import json
import logging
import queue
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
fila_avisos = queue.Queue()
conexoes_lock = threading.Lock()
conexoes_locks = {}

server_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_tcp.bind((HOST, PORTA_TCP))
server_tcp.listen()
server_tcp.settimeout(0.5)

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
    with conexoes_lock:
        lock = conexoes_locks.setdefault(conn, threading.Lock())
    with lock:
        conn.sendall(dados)
    try:
        origem, porta_origem = conn.getsockname()
        destino, porta_destino = conn.getpeername()
        logging.info("TCP | envio | %s:%s -> %s:%s | %s",
                     origem, porta_origem, destino, porta_destino, mensagem.get("tipo"))
    except OSError:
        pass


def enviar_udp(mensagem, endereco, porta):
    dados = (json.dumps(mensagem, ensure_ascii=False) + "\n").encode("utf-8")
    server_udp.sendto(dados, (endereco, porta))
    logging.info("UDP | envio | server:%s -> %s:%s | %s | atualizacao=%s",
                 PORTA_UDP, endereco, porta, mensagem.get("tipo"),
                 mensagem.get("atualizacao"))


def preparar_aviso_locked(tipo):
    """Deve ser chamada com estado_lock adquirido; preserva a ordem das atualizações."""
    global numero_atualizacao
    numero_atualizacao += 1
    nome = (participantes[maior_lance_participante]["nome"]
            if maior_lance_participante is not None else None)
    destinos = [(p["endereco"], p["porta_udp"])
                for p in participantes.values() if p["conn"] is not None]
    if tipo == "LEILAO_AVISO":
        mensagem = {"tipo": tipo, "atualizacao": numero_atualizacao,
                    "maior_lance": maior_lance, "nome_lider": nome}
    else:
        mensagem = {"tipo": tipo, "atualizacao": numero_atualizacao,
                    "vencedor": nome, "maior_lance": maior_lance}
    fila_avisos.put((mensagem, destinos))


def distribuir_avisos_udp():
    while not servidor_encerrando.is_set() or not fila_avisos.empty():
        try:
            mensagem, destinos = fila_avisos.get(timeout=0.2)
        except queue.Empty:
            continue
        try:
            for endereco, porta in destinos:
                try:
                    enviar_udp(mensagem, endereco, porta)
                except OSError as erro:
                    logging.warning("UDP | falha | server:%s -> %s:%s | %s | %s",
                                    PORTA_UDP, endereco, porta, mensagem["tipo"], erro)
        finally:
            fila_avisos.task_done()


def tempo_esgotado_locked():
    return inicio_leilao is not None and time.monotonic() >= inicio_leilao + DURACAO


def registrar_participante(nome, porta_udp, endereco, conn):
	global proximo_id

	if not isinstance(nome, str) or not nome.strip():
		return None, "Nome inválido"

	if not isinstance(porta_udp, int) or not 1 <= porta_udp <= 65535:
		return None, "Porta UDP inválida"

	nome = nome.strip()

	with estado_lock:
		if leilao_encerrado:
			return None, "Leilão encerrado"
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
				inicio_leilao = time.monotonic()

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
			# O accept() usa timeout para observar o evento de encerramento.

			return

		print("Resposta inválida. Digite 's' ou 'n'.")


def resultado_leilao():
    global leilao_iniciado, leilao_encerrado

    with estado_lock:
        if leilao_encerrado or not leilao_iniciado:
            return
        leilao_iniciado = False
        leilao_encerrado = True
        vencedor = (participantes[maior_lance_participante]["nome"]
                    if maior_lance_participante is not None else None)
        historico = [{"participante": participantes[identificador]["nome"],
                      "valor": valor} for identificador, valor in historico_lances]
        conexoes = [p["conn"] for p in participantes.values() if p["conn"] is not None]
        mensagem = {"tipo": "LEILAO_RESULTADO", "vencedor": vencedor,
                    "maior_lance": maior_lance, "historico": historico}
        preparar_aviso_locked("LEILAO_ENCERRADO")

    print("Leilão encerrado.", "Vencedor: " + vencedor if vencedor else "Sem vencedor.")
    print("Histórico de lances:")
    for lance in historico:
        print(f"  {lance['participante']}: {lance['valor']}")
    logging.info("STATE | LEILAO_ENCERRADO | vencedor=%s maior_lance=%s",
                 vencedor, mensagem["maior_lance"])
    for conn in conexoes:
        try:
            enviar_tcp(conn, mensagem)
        except OSError as erro:
            logging.warning("TCP | falha ao enviar resultado | %s", erro)


def encerrar_leilao():
    while not servidor_encerrando.is_set():
        with estado_lock:
            expirou = leilao_iniciado and tempo_esgotado_locked()
        if expirou:
            resultado_leilao()
            return
        servidor_encerrando.wait(0.05)


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
		with estado_lock:
			ja_iniciado = leilao_iniciado
		if ja_iniciado:
			enviar_tcp(conn, {"tipo": "LEILAO_INFO", "item": ITEM,
			                 "lance_minimo": LANCE_MINIMO, "duracao": DURACAO})
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
			if leilao_encerrado or (leilao_iniciado and tempo_esgotado_locked()):
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
			preparar_aviso_locked("LEILAO_AVISO")

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
		return True

	if tipo == "CONSULTAR":
		with estado_lock:
			nome_lider = (
				participantes[maior_lance_participante]["nome"]
				if maior_lance_participante is not None
				else None
			)

			if leilao_iniciado and not tempo_esgotado_locked():
				tempo_restante = max(0, int(DURACAO - (time.monotonic() - inicio_leilao)))
				situacao = "ABERTO"
			elif leilao_encerrado or (leilao_iniciado and tempo_esgotado_locked()):
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
			encerrado = leilao_encerrado
			if encerrado:
				vencedor = (
					participantes[maior_lance_participante]["nome"]
					if maior_lance_participante is not None else None
				)
				resposta = {
					"tipo": "LEILAO_RESULTADO",
					"vencedor": vencedor,
					"maior_lance": maior_lance,
					"historico": [
						{"participante": participantes[identificador]["nome"], "valor": valor}
						for identificador, valor in historico_lances
					],
				}
			else:
				resposta = {"tipo": "RESULTADO_ERROR",
				            "mensagem": "O leilão ainda não foi encerrado"}
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

				logging.info("TCP | recebimento | %s:%s -> server:%s | %s",
				             addr[0], addr[1], PORTA_TCP,
				             mensagem.get("tipo") if isinstance(mensagem, dict) else "INVALID")
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

		with conexoes_lock:
			conexoes_locks.pop(conn, None)
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
	threading.Thread(target=distribuir_avisos_udp, daemon=True).start()

	while not servidor_encerrando.is_set():
		try:
			conn, addr = server_tcp.accept()
		except socket.timeout:
			continue
		except OSError:
			break
		if servidor_encerrando.is_set():
			conn.close()
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

	servidor_encerrando.set()
	with estado_lock:
		conexoes = [p["conn"] for p in participantes.values() if p["conn"] is not None]
	for conn in conexoes:
		try:
			conn.shutdown(socket.SHUT_RDWR)
		except OSError:
			pass
		conn.close()
	print("Servidor encerrado.")


if __name__ == "__main__":
	try:
		main()
	except KeyboardInterrupt:
		print("\nServidor encerrado.")
	finally:
		server_tcp.close()
		server_udp.close()
