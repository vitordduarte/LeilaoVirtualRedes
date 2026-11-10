import socket
import threading
import json
from time import time

HOST = "0.0.0.0"
PORTA_TCP = 12346
PORTA_UDP = 12347

#dicionario
participantes = {}
proximo_id = 1


####variavel para controlar o estado do leilão, aqui pensei no servidor ser o organizador do leilão, mas se preferirem poderia ser o cliente
leilao_iniciado = False


# variáveis do leilão
item = "Notebook"
lance_minimo = 500
duracao = 60

maior_lance = 0
maior_lance_participante = None
historico_lances = []

inicio_leilao = None


# Criação do socket TCP
server_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_tcp.bind((HOST, PORTA_TCP))
server_tcp.listen()

# Criação do socket UDP
server_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server_udp.bind((HOST, PORTA_UDP))

print(f"Servidor TCP aguardando na porta {PORTA_TCP}")
print(f"Servidor UDP aguardando na porta {PORTA_UDP}")




def atender_cliente(conn, addr):
    global maior_lance, maior_lance_participante, historico_lances, leilao_iniciado, inicio_leilao


    # função responsável pelo cliente
    print(f"Atendendo {addr}")

    #recebimento
    dados = b""
    while True:
        # recebendo dados
        bloco_recebido = conn.recv(1024)
        if not bloco_recebido:   
            break
        dados += bloco_recebido

        if b"\n" in dados:
            break

    #converter dados para JSON
    mensagem = json.loads(dados.decode())

    #cadastro participante
    
    if mensagem.get("tipo") == "REGISTER":       
        #extrair nome e porta UDP
        nome = mensagem.get("nome")
        porta_udp = mensagem.get("porta_udp")

        #gerar id
        global proximo_id
        id_participante = proximo_id
        proximo_id += 1 

        #guardar no dicionario
        participantes[id_participante] = {
            "nome": nome,
            "porta_udp": porta_udp,
            "endereco": addr[0],
            "conn": conn
        }

      #confirmacao para o cliente
        resposta = {  
            "tipo": "REGISTER_OK",
            "id": id_participante,
            "mensagem": "Cadastro realizado com sucesso"
        }

        #string json
        resposta_str = json.dumps(resposta) + "\n"
        conn.sendall(resposta_str.encode())

        #validar dados
        if not nome or not porta_udp or porta_udp < 1 or porta_udp > 65535:
            resposta = {
                "tipo": "REGISTER_ERROR",
                "mensagem": "Nome ou porta UDP inválidos"
            }

            resposta_str = json.dumps(resposta) + "\n"
            conn.sendall(resposta_str.encode())
            conn.close()
            return

        #verificar se o nome já está cadastrado
        for participante in participantes.values():
            if participante["nome"] == nome:
                resposta = {
                    "tipo": "REGISTER_ERROR",
                    "mensagem": "Nome já cadastrado"
                }

                resposta_str = json.dumps(resposta) + "\n"
                conn.sendall(resposta_str.encode())
                conn.close()
                return


    if mensagem.get("tipo") == "LANCE" and leilao_iniciado == True:
        #receber lance do participante
        
        #identificar participante pela conexao tcp
        id_participante = None
        for id_participante, participante in participantes.items():
            if participante["conn"] == conn:
                id_encontrado = id_participante
                break

        if id_encontrado is None:
            resposta = {
                "tipo": "LANCE_ERROR",
                "mensagem": "Participante não cadastrado"
            }
            resposta_str = json.dumps(resposta) + "\n"
            conn.sendall(resposta_str.encode())
            return

        
        valor_lance = mensagem.get("valor")

        #validação valor lance
        if not isinstance(valor_lance, int) or valor_lance <=0: #verifica se valor é inteiro
            resposta = {
                "tipo": "LANCE_ERROR",
                "mensagem": "Valor do lance inválido"
            }
            resposta_str = json.dumps(resposta) + "\n"
            conn.sendall(resposta_str.encode())
            return

        #validar lance maior que o atual
        if valor_lance <= maior_lance:
            resposta = {
                "tipo": "LANCE_ERROR",
                "mensagem": "Lance deve superar o maior lance atual"
            }
            resposta_str = json.dumps(resposta) + "\n"
            conn.sendall(resposta_str.encode())
            return
        
        #validar se nao houve lance aceito
        if maior_lance == 0 and valor_lance < lance_minimo:
            resposta = {
                "tipo": "LANCE_ERROR",
                "mensagem": "Lance abaixo do mínimo"
            }
            resposta_str = json.dumps(resposta) + "\n"
            conn.sendall(resposta_str.encode())
            return


        #registrar lance
        print(f"Participante {id_participante} deu um lance de {valor_lance}")

        historico_lances.append((id_participante, valor_lance))

        #atualizar maior lance
        if valor_lance > maior_lance:
            maior_lance = valor_lance
            maior_lance_participante = id_participante

        enviar_aviso_lance_udp()  # enviar aviso de lance maior via UDP


        #resposta de sucesso
        resposta = {
            "tipo": "LANCE_OK",
            "mensagem": "Lance registrado com sucesso"
        }
        resposta_str = json.dumps(resposta) + "\n"
        conn.sendall(resposta_str.encode())


    elif mensagem.get("tipo") == "LANCE" and leilao_iniciado == False:
        resposta = {
            "tipo": "LANCE_ERROR",
            "mensagem": "Leilão ainda não iniciado"
        }
        resposta_str = json.dumps(resposta) + "\n"
        conn.sendall(resposta_str.encode())
        return


    #variaveis para consulta
    nome_lider = None

    if maior_lance_participante is not None:
        nome_lider = participantes[maior_lance_participante]["nome"]

    tempo_restante = max(0, duracao - (time.time() - inicio_leilao))

    situacao_leilao = "Leilão aberto" if leilao_iniciado else "Leilão fechado"

    if mensagem.get("tipo") == "CONSULTAR":
        #enviar informações do leilão para o participante
        resposta = {
            "tipo": "CONSULTAR",
            "item": item,
            "maior_lance": maior_lance,
            "tempo_restante": tempo_restante,
            "nome_lider": nome_lider,
            "situacao": situacao_leilao
        }
        resposta_str = json.dumps(resposta) + "\n"
        conn.sendall(resposta_str.encode())


def iniciar_leilao():
    global leilao_iniciado, inicio_leilao
    
    #iniciar leilao pelo organizador (servidor)
    while True:
        if input("Deseja iniciar o leilão? (s/n): ").lower() == "s":
            global leilao_iniciado
            leilao_iniciado = True
            inicio_leilao = time.time()
            print("Iniciando leilão...")
            break   
        else:
            print("Leilão não iniciado.")
            

#  thread organizador
thread = threading.Thread(target=iniciar_leilao, args=())
thread.start()

#  thread encerrar leilão
thread = threading.Thread(target=encerrar_leilao, args=())
thread.start()


def apresentar_itens():
    #apresentar itens do leilão
    print(f"Item: {item}")
    print(f"Lance mínimo: {lance_minimo}")
    print(f"Duração: {duracao} segundos")

#enviar informações do leilão para os participantes via tcp
def enviar_informacoes_leilao():
    while True:
        if leilao_iniciado:
            for id_participante, participante in participantes.items():

                conn = participante["conn"] # recupera a conexão TCP

                mensagem = {
                    "tipo": "LEILAO_INFO",
                    "item": item,
                    "lance_minimo": lance_minimo,
                    "duracao": duracao
                }

                mensagem_str = json.dumps(mensagem) + "\n"
                conn.sendall(mensagem_str.encode())
            break


 #aviso lance maior
def enviar_aviso_lance_udp():
        for id_participante, participante in participantes.items():
            endereco = participante["endereco"]
            porta_udp = participante["porta_udp"]

            mensagem = {
                "tipo": "LEILAO_AVISO",
                "maior_lance": maior_lance,
                "nome_lider": participantes[maior_lance_participante]["nome"] if maior_lance_participante is not None else None
            }

            mensagem_str = json.dumps(mensagem) + "\n"
            server_udp.sendto(mensagem_str.encode(), (endereco, porta_udp))

#aviso leilão encerrado
def enviar_aviso_encerramento_udp():
        for id_participante, participante in participantes.items():
            endereco = participante["endereco"]
            porta_udp = participante["porta_udp"]

            mensagem = {
                "tipo": "LEILAO_ENCERRADO",
                "vencedor": participantes[maior_lance_participante]["nome"] if maior_lance_participante is not None else None,
                "maior_lance": maior_lance
            }

            mensagem_str = json.dumps(mensagem) + "\n"
            server_udp.sendto(mensagem_str.encode(), (endereco, porta_udp))





#resultado do leilão
def resultado_leilao():
    global leilao_iniciado, maior_lance, maior_lance_participante, historico_lances

    leilao_iniciado = False

    if maior_lance_participante is None:
        print("Leilão encerrado. Nenhum lance foi registrado.")
    else: maior_lance_participante is not None:
        nome_vencedor = participantes[maior_lance_participante]["nome"]
        print(f"Leilão encerrado. Vencedor: {nome_vencedor} com lance de {maior_lance}")

    #enviar aos clientes o resultado do leilão
    for id_participante, participante in participantes.items():

        conn = participante["conn"] # recupera a conexão TCP

        mensagem = {
            "tipo": "LEILAO_RESULTADO",
            "vencedor": nome_vencedor if maior_lance_participante is not None else None,
            "maior_lance": maior_lance
        }

        mensagem_str = json.dumps(mensagem) + "\n"
        conn.sendall(mensagem_str.encode())


    #apresentar histórico de lances
    print("Histórico de lances:")

    leilao_iniciado = False

    enviar_aviso_encerramento_udp()  # enviar aviso de encerramento via UDP



# encerrar leilão após o tempo determinado
def encerrar_leilao():
    global leilao_iniciado, inicio_leilao

    while True:
        if leilao_iniciado and (time.time() - inicio_leilao) >= duracao:
            print("Tempo do leilão esgotado.")
            resultado_leilao()
            break

        time.sleep(0.1) #para evitar uso excessivo
        
while True:
    # aceitar conexão
    conn, addr = server_tcp.accept()

    # criando thread
    thread = threading.Thread(target=atender_cliente, args=(conn, addr))
    thread.start()



  



finally:
    server_tcp.close()
    server_udp.close()