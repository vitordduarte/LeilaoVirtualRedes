import json
import logging
import socket
import threading
import time
from pathlib import Path

HOST = "0.0.0.0"
PORTA_TCP = 12346
PORTA_UDP = 12347

ITEM = "Notebook"
LANCE_MINIMO = 500
DURACAO = 60

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

participantes = {}
proximo_id = 1

leilao_iniciado = False
leilao_encerrado = False
inicio_leilao = None

maior_lance = 0
maior_lance_participante = None
historico_lances = []
numero_atualizacao = 0

estado_lock = threading.Lock()
servidor_encerrando = threading.Event()

server_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_tcp.bind((HOST, PORTA_TCP))
server_tcp.listen()

server_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_udp.bind((HOST, PORTA_UDP))

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

print(f"Servidor TCP aguardando na porta {PORTA_TCP}")
print(f"Servidor UDP aguardando na porta {PORTA_UDP}")


def enviar_tcp(conn, mensagem):
	dados = (json.dumps(mensagem, ensure_ascii=False) + "\n").encode("utf-8")
	conn.sendall(dados)


def enviar_udp(mensagem, endereco, porta):
	dados = (json.dumps(mensagem, ensure_ascii=False) + "\n").encode("utf-8")
	server_udp.sendto(dados, (endereco, porta))


def registrar_participante(nome, porta_udp, endereco, conn):
	global proximo_id

	if not isinstance(nome, str) or not nome.strip():
		return None, "Nome inválido"

	if not isinstance(porta_udp, int) or not 1 <= porta_udp <= 65535:
		return None, "Porta UDP inválida"

	nome = nome.strip()

	with estado_lock:
		for participante in participantes.values():
			if participante["nome"].lower() == nome.lower():
				return None, "Nome já cadastrado"

		id_participante = proximo_id
		proximo_id += 1

		participantes[id_participante] = {
			"nome": nome,
			"porta_udp": porta_udp,
			"endereco": endereco,
			"conn": conn,
		}

	logging.info(
		"TCP | REGISTER | %s:%s -> server:%s | participant_id=%s name=%s udp_port=%s",
		endereco,
		conn.getpeername()[1],
		PORTA_TCP,
		id_participante,
		nome,
		porta_udp,
	)

	return id_participante, None


def obter_participante_por_conexao(conn):
	with estado_lock:
		for id_participante, participante in participantes.items():
			if participante["conn"] is conn:
				return id_participante
	return None


def enviar_aviso_lance_udp():
	with estado_lock:
		global numero_atualizacao
		numero_atualizacao += 1
		atualizacao = numero_atualizacao

		nome_lider = (
			participantes[maior_lance_participante]["nome"]
			if maior_lance_participante is not None
			else None
		)

		destinos = [
			(participante["endereco"], participante["porta_udp"])
			for participante in participantes.values()
		]

		mensagem = {
			"tipo": "LEILAO_AVISO",
			"atualizacao": atualizacao,
			"maior_lance": maior_lance,
			"nome_lider": nome_lider,
		}

	for endereco, porta_udp in destinos:
		try:
			enviar_udp(mensagem, endereco, porta_udp)
		except OSError as erro:
			logging.warning(
				"UDP | LEILAO_AVISO | falha para %s:%s | %s",
				endereco,
				porta_udp,
				erro,
			)


def enviar_aviso_encerramento_udp():
	with estado_lock:
		global numero_atualizacao
		numero_atualizacao += 1
		atualizacao = numero_atualizacao

		vencedor = (
			participantes[maior_lance_participante]["nome"]
			if maior_lance_participante is not None
			else None
		)

		destinos = [
			(participante["endereco"], participante["porta_udp"])
			for participante in participantes.values()
		]

		mensagem = {
			"tipo": "LEILAO_ENCERRADO",
			"atualizacao": atualizacao,
			"vencedor": vencedor,
			"maior_lance": maior_lance,
		}

	for endereco, porta_udp in destinos:
		try:
			enviar_udp(mensagem, endereco, porta_udp)
		except OSError as erro:
			logging.warning(
				"UDP | LEILAO_ENCERRADO | falha para %s:%s | %s",
				endereco,
				porta_udp,
				erro,
			)


def enviar_informacoes_leilao():
	mensagem = {
		"tipo": "LEILAO_INFO",
		"item": ITEM,
		"lance_minimo": LANCE_MINIMO,
		"duracao": DURACAO,
	}

	with estado_lock:
		conexoes = [
			p["conn"] for p in participantes.values()
			if p["conn"] is not None
		]

	for conn in conexoes:
		try:
			enviar_tcp(conn, mensagem)
		except OSError:
			pass


def iniciar_leilao():
	global leilao_iniciado, leilao_encerrado, inicio_leilao

	while True:
		resposta = input("Deseja iniciar o leilão? (s/n): ").strip().lower()

		if resposta == "s":
			with estado_lock:
				if not participantes:
					print("Não é possível iniciar o leilão sem participantes.")
					continue

				leilao_iniciado = True
				leilao_encerrado = False
				inicio_leilao = time.time()

			print("Iniciando leilão...")
			logging.info(
				"STATE | LEILAO_INICIADO | item=%s lance_minimo=%s duracao=%s",
				ITEM,
				LANCE_MINIMO,
				DURACAO,
			)

			enviar_informacoes_leilao()
			return

		if resposta == "n":
			print("Leilão cancelado.")
			logging.info("STATE | LEILAO_CANCELADO")

			servidor_encerrando.set()
			server_tcp.close()
			server_udp.close()

			return

		print("Resposta inválida. Digite 's' ou 'n'.")


def resultado_leilao():
	global leilao_iniciado, leilao_encerrado

	with estado_lock:
		if leilao_encerrado:
			return

		leilao_iniciado = False
		leilao_encerrado = True

		if maior_lance_participante is not None:
			nome_vencedor = participantes[maior_lance_participante]["nome"]
			valor_vencedor = maior_lance
			historico = list(historico_lances)
		else:
			nome_vencedor = None
			valor_vencedor = 0
			historico = list(historico_lances)

		conexoes = [
			p["conn"] for p in participantes.values()
			if p["conn"] is not None
		]

	if nome_vencedor is None:
		print("Leilão encerrado. Nenhum lance foi aceito.")
	else:
		print(
			f"Leilão encerrado. Vencedor: {nome_vencedor} "
			f"com lance de {valor_vencedor}"
		)

	print("Histórico de lances:")
	for lance in historico:
		id_participante, valor = lance
		with estado_lock:
			participante = participantes.get(id_participante)
			nome = participante["nome"] if participante else "Desconhecido"
		print(f"  {nome}: {valor}")

	mensagem = {
		"tipo": "LEILAO_RESULTADO",
		"vencedor": nome_vencedor,
		"maior_lance": valor_vencedor,
		"historico": [
			{
				"participante": (
					participantes[id_participante]["nome"]
					if id_participante in participantes
					else "Desconhecido"
				),
				"valor": valor,
			}
			for id_participante, valor in historico
		],
	}

	logging.info(
		"STATE | LEILAO_ENCERRADO | vencedor=%s maior_lance=%s",
		nome_vencedor,
		valor_vencedor,
	)

	for conn in conexoes:
		try:
			enviar_tcp(conn, mensagem)
		except OSError:
			pass

	enviar_aviso_encerramento_udp()


def encerrar_leilao():
	while True:
		with estado_lock:
			iniciado = leilao_iniciado
			inicio = inicio_leilao

		if iniciado and inicio is not None:
			tempo_decorrido = time.time() - inicio
			if tempo_decorrido >= DURACAO:
				print("Tempo do leilão esgotado.")
				resultado_leilao()
				return

		time.sleep(0.1)


def processar_mensagem(conn, addr, mensagem):
	global maior_lance, maior_lance_participante

	tipo = mensagem.get("tipo")

	if tipo == "REGISTER":
		id_participante, erro = registrar_participante(
			mensagem.get("nome"),
			mensagem.get("porta_udp"),
			addr[0],
			conn,
		)

		if erro:
			logging.warning(
				"TCP | REGISTER_ERROR | %s:%s -> server:%s | reason=%s",
				addr[0],
				addr[1],
				PORTA_TCP,
				erro,
			)
			enviar_tcp(
				conn,
				{
					"tipo": "REGISTER_ERROR",
					"mensagem": erro,
				},
			)
			return False

		enviar_tcp(
			conn,
			{
				"tipo": "REGISTER_OK",
				"id": id_participante,
				"mensagem": "Cadastro realizado com sucesso",
			},
		)
		return True

	id_participante = obter_participante_por_conexao(conn)

	if id_participante is None:
		enviar_tcp(
			conn,
			{
				"tipo": "ERROR",
				"mensagem": "Participante não cadastrado",
			},
		)
		return True

	if tipo == "LANCE":
		valor_lance = mensagem.get("valor")

		with estado_lock:
			if leilao_encerrado:
				erro = "Leilão encerrado"
			elif not leilao_iniciado:
				erro = "Leilão ainda não iniciado"
			elif not isinstance(valor_lance, int) or isinstance(valor_lance, bool) or valor_lance <= 0:
				erro = "Valor do lance inválido"
			elif maior_lance == 0 and valor_lance < LANCE_MINIMO:
				erro = "Lance abaixo do mínimo"
			elif valor_lance <= maior_lance:
				erro = "Lance deve superar o maior lance atual"
			else:
				erro = None
				maior_lance = valor_lance
				maior_lance_participante = id_participante
				historico_lances.append((id_participante, valor_lance))

		if erro:
			logging.info(
				"TCP | LANCE_REJEITADO | participant_id=%s valor=%s | reason=%s",
				id_participante,
				valor_lance,
				erro,
			)
			enviar_tcp(
				conn,
				{
					"tipo": "LANCE_ERROR",
					"mensagem": erro,
				},
			)
			return True

		print(
			f"Participante {id_participante} deu um lance de {valor_lance}"
		)
		logging.info(
			"STATE | LANCE_ACEITO | participant_id=%s valor=%s",
			id_participante,
			valor_lance,
		)

		enviar_tcp(
			conn,
			{
				"tipo": "LANCE_OK",
				"mensagem": "Lance registrado com sucesso",
				"valor": valor_lance,
			},
		)
		enviar_aviso_lance_udp()
		return True

	if tipo == "CONSULTAR":
		with estado_lock:
			nome_lider = (
				participantes[maior_lance_participante]["nome"]
				if maior_lance_participante is not None
				else None
			)

			if leilao_iniciado and inicio_leilao is not None:
				tempo_restante = max(
					0, int(DURACAO - (time.time() - inicio_leilao))
				)
				situacao = "ABERTO"
			elif leilao_encerrado:
				tempo_restante = 0
				situacao = "ENCERRADO"
			else:
				tempo_restante = DURACAO
				situacao = "AGUARDANDO"

			resposta = {
				"tipo": "SITUACAO",
				"item": ITEM,
				"lance_minimo": LANCE_MINIMO,
				"maior_lance": maior_lance,
				"nome_lider": nome_lider,
				"tempo_restante": tempo_restante,
				"situacao": situacao,
			}

		logging.info(
			"TCP | CONSULTAR | participant_id=%s | situacao=%s",
			id_participante,
			resposta["situacao"],
		)
		enviar_tcp(conn, resposta)
		return True

	if tipo == "RESULTADO":
		with estado_lock:
			if not leilao_encerrado:
				enviar_tcp(
					conn,
					{
						"tipo": "RESULTADO_ERROR",
						"mensagem": "O leilão ainda não foi encerrado",
					},
				)
				return True

			vencedor = (
				participantes[maior_lance_participante]["nome"]
				if maior_lance_participante is not None
				else None
			)

			resposta = {
				"tipo": "LEILAO_RESULTADO",
				"vencedor": vencedor,
				"maior_lance": maior_lance,
				"historico": [
					{
						"participante": participantes[id_participante]["nome"],
						"valor": valor,
					}
					for id_participante, valor in historico_lances
				],
			}

		enviar_tcp(conn, resposta)
		return True

	enviar_tcp(
		conn,
		{
			"tipo": "ERROR",
			"mensagem": "Tipo de mensagem desconhecido",
		},
	)
	logging.warning(
		"TCP | ERROR | %s:%s -> server:%s | unknown_type=%s",
		addr[0],
		addr[1],
		PORTA_TCP,
		tipo,
	)
	return True


def atender_cliente(conn, addr):
	print(f"Atendendo {addr}")
	buffer = b""
	registrado = False

	try:
		while True:
			bloco_recebido = conn.recv(4096)

			if not bloco_recebido:
				break

			buffer += bloco_recebido

			while b"\n" in buffer:
				linha, buffer = buffer.split(b"\n", 1)

				if not linha.strip():
					continue

				try:
					mensagem = json.loads(linha.decode("utf-8"))
				except (UnicodeDecodeError, json.JSONDecodeError) as erro:
					logging.warning(
						"TCP | MALFORMED | %s:%s -> server:%s | error=%s",
						addr[0],
						addr[1],
						PORTA_TCP,
						erro,
					)
					enviar_tcp(
						conn,
						{
							"tipo": "ERROR",
							"mensagem": "Mensagem JSON inválida",
						},
					)
					continue

				if not isinstance(mensagem, dict):
					enviar_tcp(
						conn,
						{
							"tipo": "ERROR",
							"mensagem": "Mensagem deve ser um objeto JSON",
						},
					)
					continue

				if mensagem.get("tipo") == "REGISTER":
					if registrado:
						enviar_tcp(
							conn,
							{
								"tipo": "REGISTER_ERROR",
								"mensagem": "Participante já cadastrado nesta conexão",
							},
						)
						continue

					registrado = processar_mensagem(conn, addr, mensagem)
					continue

				if not registrado:
					registrado = obter_participante_por_conexao(conn) is not None

				if not processar_mensagem(conn, addr, mensagem):
					return

	except (ConnectionResetError, BrokenPipeError, OSError) as erro:
		logging.info(
			"TCP | DISCONNECT | %s:%s -> server:%s | %s",
			addr[0],
			addr[1],
			PORTA_TCP,
			erro,
		)
	finally:
		id_participante = obter_participante_por_conexao(conn)

		if id_participante is not None:
			with estado_lock:
				participante = participantes.get(id_participante)
				if participante is not None:
					participante["conn"] = None

			logging.info(
				"STATE | PARTICIPANT_DISCONNECTED | participant_id=%s",
				id_participante,
			)

		conn.close()
		print(f"Conexão encerrada: {addr}")


def apresentar_itens():
	print(f"Item: {ITEM}")
	print(f"Lance mínimo: {LANCE_MINIMO}")
	print(f"Duração: {DURACAO} segundos")


def main():
	apresentar_itens()

	threading.Thread(
		target=iniciar_leilao,
		daemon=True
	).start()

	threading.Thread(
		target=encerrar_leilao,
		daemon=True
	).start()

	while not servidor_encerrando.is_set():
		try:
			conn, addr = server_tcp.accept()
		except OSError:
			break

		logging.info(
			"TCP | CONNECT | %s:%s -> server:%s",
			addr[0],
			addr[1],
			PORTA_TCP,
		)

		threading.Thread(
			target=atender_cliente,
			args=(conn, addr),
			daemon=True,
		).start()

	print("Servidor encerrado.")


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		print("\nServidor encerrado.")
	finally:
		server_tcp.close()
		server_udp.close()
