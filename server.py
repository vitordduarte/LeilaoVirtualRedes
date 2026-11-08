import socket
import threading
import json

HOST = "0.0.0.0"
PORTA_TCP = 12346
PORTA_UDP = 12347

#dicionario
participantes = {}
proximo_id = 1



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
            "endereco": addr[0]
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



        
while True:
    # aceitar conexão
    conn, addr = server_tcp.accept()

    # criando thread
    thread = threading.Thread(target=atender_cliente, args=(conn, addr))
    thread.start()

  



finally:
    server_tcp.close()
    server_udp.close()