import argparse
import json
import logging
import socket
import threading
from pathlib import Path

PORTA_TCP = 12346
PORTA_UDP_SERVIDOR = 12347
TAMANHO_BUFFER = 4096

encerrar_cliente = threading.Event()
console_lock = threading.Lock()
resposta_recebida = threading.Event()
respostas_esperadas = frozenset()


class LeitorTCP:
    def __init__(self, conexao):
        self.conexao = conexao
        self.buffer = b""

    def receber_mensagem(self):
        while b"\n" not in self.buffer:
            bloco = self.conexao.recv(TAMANHO_BUFFER)
            if not bloco:
                raise ConnectionError("Conexão encerrada pelo servidor")
            self.buffer += bloco

        linha, self.buffer = self.buffer.split(b"\n", 1)
        mensagem = json.loads(linha.decode("utf-8"))
        validar_mensagem(mensagem)
        return mensagem


def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description="Cliente do leilão virtual em rede"
    )
    parser.add_argument(
        "--servidor",
        default="127.0.0.1",
        help="IP ou nome do servidor (padrão: 127.0.0.1)",
    )
    parser.add_argument(
        "--porta-udp",
        type=int,
        required=True,
        help="porta UDP local para receber avisos; use uma porta diferente por cliente",
    )
    argumentos = parser.parse_args()
    if not 1 <= argumentos.porta_udp <= 65535:
        parser.error("--porta-udp deve estar entre 1 e 65535")
    return argumentos


def tipo_mensagem(mensagem):
    return str(mensagem.get("tipo", "DESCONHECIDO"))


def validar_mensagem(mensagem):
    if not isinstance(mensagem, dict):
        raise ValueError("A mensagem recebida não é um objeto JSON")

    nome_opcional = (str, type(None))
    campos_por_tipo = {
        "REGISTER_OK": {"id": int, "mensagem": str},
        "REGISTER_ERROR": {"mensagem": str},
        "ERROR": {"mensagem": str},
        "LANCE_OK": {"valor": int, "mensagem": str},
        "LANCE_ERROR": {"mensagem": str},
        "RESULTADO_ERROR": {"mensagem": str},
        "LEILAO_INFO": {"item": str, "lance_minimo": int, "duracao": int},
        "SITUACAO": {
            "item": str, "lance_minimo": int, "maior_lance": int,
            "nome_lider": nome_opcional, "tempo_restante": int, "situacao": str,
        },
        "LEILAO_RESULTADO": {
            "vencedor": nome_opcional, "maior_lance": int, "historico": list,
        },
        "LEILAO_AVISO": {
            "atualizacao": int, "maior_lance": int, "nome_lider": nome_opcional,
        },
        "LEILAO_ENCERRADO": {
            "atualizacao": int, "vencedor": nome_opcional, "maior_lance": int,
        },
    }
    tipo = mensagem.get("tipo")
    if not isinstance(tipo, str) or tipo not in campos_por_tipo:
        raise ValueError("Tipo de mensagem inválido ou desconhecido")

    def validar_campos(objeto, campos):
        for campo, esperado in campos.items():
            if campo not in objeto or not isinstance(objeto[campo], esperado):
                raise ValueError(f"Campo ausente ou inválido: {campo}")
            if esperado is int and isinstance(objeto[campo], bool):
                raise ValueError(f"Campo inteiro inválido: {campo}")

    validar_campos(mensagem, campos_por_tipo[tipo])
    if tipo == "LEILAO_RESULTADO":
        for lance in mensagem["historico"]:
            if not isinstance(lance, dict):
                raise ValueError("Entrada inválida no histórico de lances")
            validar_campos(lance, {"participante": str, "valor": int})


def enviar_tcp(conexao, mensagem):
    dados = (json.dumps(mensagem, ensure_ascii=False) + "\n").encode("utf-8")
    conexao.sendall(dados)
    logging.info(
        "TCP | envio | %s:%s -> %s:%s | %s",
        *conexao.getsockname(),
        *conexao.getpeername(),
        tipo_mensagem(mensagem),
    )


def exibir_mensagem(mensagem, protocolo):
    tipo = tipo_mensagem(mensagem)
    with console_lock:
        if tipo == "LEILAO_INFO":
            print(
                "\nLeilão iniciado: "
                f"{mensagem['item']} | mínimo: {mensagem['lance_minimo']} | "
                f"duração: {mensagem['duracao']}s"
            )
        elif tipo == "LANCE_OK":
            print(f"\nLance aceito: {mensagem.get('valor')}")
        elif tipo in ("LANCE_ERROR", "REGISTER_ERROR", "RESULTADO_ERROR", "ERROR"):
            print(f"\nOperação rejeitada: {mensagem.get('mensagem', tipo)}")
        elif tipo == "SITUACAO":
            lider = mensagem.get("nome_lider") or "sem lances"
            print(
                f"\nSituação: {mensagem['situacao']} | item: {mensagem['item']} | "
                f"maior lance: {mensagem['maior_lance']} ({lider}) | "
                f"tempo restante: {mensagem['tempo_restante']}s"
            )
        elif tipo == "LEILAO_RESULTADO":
            vencedor = mensagem.get("vencedor")
            if vencedor is None:
                print("\nLeilão encerrado sem lances aceitos.")
            else:
                print(
                    f"\nResultado: {vencedor} venceu com "
                    f"{mensagem['maior_lance']}"
                )
            for lance in mensagem.get("historico", []):
                print(
                    f"  {lance['participante']}: {lance['valor']}"
                )
        elif tipo == "LEILAO_AVISO":
            lider = mensagem.get("nome_lider") or "sem lances"
            print(
                f"\n[UDP #{mensagem['atualizacao']}] Novo maior lance: "
                f"{mensagem['maior_lance']} ({lider})"
            )
        elif tipo == "LEILAO_ENCERRADO":
            vencedor = mensagem.get("vencedor") or "sem vencedor"
            print(
                f"\n[UDP #{mensagem['atualizacao']}] "
                f"Leilão encerrado. Vencedor: {vencedor}."
            )
        elif tipo == "REGISTER_OK":
            print(
                f"Cadastro realizado. Seu identificador é "
                f"{mensagem['id']}."
            )
        else:
            print(f"\n[{protocolo}] {mensagem}")


def receber_tcp(leitor):
    try:
        while not encerrar_cliente.is_set():
            try:
                mensagem = leitor.receber_mensagem()
            except ValueError as erro:
                logging.warning(
                    "TCP | mensagem malformada de %s:%s | %s",
                    *leitor.conexao.getpeername(), erro,
                )
                continue
            logging.info(
                "TCP | recebimento | %s:%s -> %s:%s | %s",
                *leitor.conexao.getpeername(),
                *leitor.conexao.getsockname(),
                tipo_mensagem(mensagem),
            )
            exibir_mensagem(mensagem, "TCP")
            if tipo_mensagem(mensagem) in respostas_esperadas:
                resposta_recebida.set()
    except (ConnectionError, OSError) as erro:
        if not encerrar_cliente.is_set():
            logging.warning("TCP | desconexão/erro | %s", erro)
            with console_lock:
                print(f"\nConexão TCP encerrada: {erro}")
            encerrar_cliente.set()


def receber_udp(soquete_udp):
    while not encerrar_cliente.is_set():
        try:
            dados, origem = soquete_udp.recvfrom(TAMANHO_BUFFER)
        except socket.timeout:
            continue
        except OSError as erro:
            if not encerrar_cliente.is_set():
                logging.warning("UDP | erro de recebimento | %s", erro)
                with console_lock:
                    print(f"\nErro no recebimento UDP: {erro}")
                encerrar_cliente.set()
            return

        try:
            mensagem = json.loads(dados.decode("utf-8"))
            validar_mensagem(mensagem)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as erro:
            logging.warning("UDP | mensagem malformada de %s:%s | %s", *origem, erro)
            continue

        logging.info(
            "UDP | recebimento | %s:%s -> cliente:%s | %s",
            *origem,
            soquete_udp.getsockname()[1],
            tipo_mensagem(mensagem),
        )
        exibir_mensagem(mensagem, "UDP")


def executar_menu(conexao):
    global respostas_esperadas

    opcoes = {
        "1": ("LANCE", "valor"),
        "2": ("CONSULTAR", None),
        "3": ("RESULTADO", None),
    }
    respostas_por_operacao = {
        "LANCE": frozenset({"LANCE_OK", "LANCE_ERROR", "ERROR"}),
        "CONSULTAR": frozenset({"SITUACAO", "ERROR"}),
        "RESULTADO": frozenset({"LEILAO_RESULTADO", "RESULTADO_ERROR", "ERROR"}),
    }

    while not encerrar_cliente.is_set():
        with console_lock:
            print("\n1) Dar lance  2) Consultar situação  3) Consultar resultado  q) Sair")
        opcao = input("Escolha: ").strip().lower()

        if opcao == "q":
            return
        if opcao not in opcoes:
            with console_lock:
                print("Opção inválida.")
            continue

        tipo, campo = opcoes[opcao]
        mensagem = {"tipo": tipo}
        if campo == "valor":
            valor_texto = input("Valor inteiro positivo do lance: ").strip()
            try:
                valor = int(valor_texto)
            except ValueError:
                with console_lock:
                    print("Informe um número inteiro positivo.")
                continue
            if valor <= 0:
                with console_lock:
                    print("Informe um número inteiro positivo.")
                continue
            mensagem[campo] = valor
        # Registra a espera antes do envio para não perder uma resposta rápida.
        respostas_esperadas = respostas_por_operacao[tipo]
        resposta_recebida.clear()
        enviar_tcp(conexao, mensagem)
        while not resposta_recebida.wait(timeout=0.1):
            if encerrar_cliente.is_set():
                return


def main():
    argumentos = configurar_argumentos()
    nome = input("Seu nome no leilão: ").strip()
    if not nome:
        raise ValueError("O nome do participante não pode ficar vazio")

    diretorio_logs = Path(__file__).resolve().parent.parent / "logs"
    diretorio_logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=diretorio_logs / f"cliente-{argumentos.porta_udp}.log",
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    soquete_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    soquete_udp.bind(("", argumentos.porta_udp))
    soquete_udp.settimeout(0.5)

    conexao = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        conexao.connect((argumentos.servidor, PORTA_TCP))
        leitor = LeitorTCP(conexao)
        enviar_tcp(
            conexao,
            {"tipo": "REGISTER", "nome": nome, "porta_udp": argumentos.porta_udp},
        )
        resposta = leitor.receber_mensagem()
        logging.info(
            "TCP | recebimento | %s:%s -> %s:%s | %s",
            *conexao.getpeername(),
            *conexao.getsockname(),
            tipo_mensagem(resposta),
        )
        exibir_mensagem(resposta, "TCP")
        if tipo_mensagem(resposta) != "REGISTER_OK":
            return

        threading.Thread(
            target=receber_tcp, args=(leitor,), daemon=True
        ).start()
        threading.Thread(
            target=receber_udp, args=(soquete_udp,), daemon=True
        ).start()
        executar_menu(conexao)
    finally:
        encerrar_cliente.set()
        conexao.close()
        soquete_udp.close()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as erro:
        print(f"Não foi possível iniciar o cliente: {erro}")
