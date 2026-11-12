# Leilão virtual em rede

Trabalho Prático 2 da disciplina **Redes de Computadores: Aplicação e Transporte**, ministrada pelo professor **Elvandi da Silva Júnior**.

**Tema escolhido:** opção 3 — Leilão virtual em rede.

**Integrantes:** Gabriel Pires de Farias, Henrique Colling e Vitor Daniel Duarte.

## Funcionamento

A aplicação utiliza sockets IPv4 em uma arquitetura cliente-servidor, com interface textual. O servidor mantém o estado oficial de um leilão de um único item e atende vários clientes simultaneamente.

O cadastro, a apresentação do item, os lances, suas confirmações, as consultas e o resultado utilizam **TCP**. Os avisos de novo maior lance e de encerramento utilizam **UDP unicast**, enviados individualmente aos participantes conectados.

O item padrão é um **Notebook**, com lance mínimo de **500** e duração de **60 segundos**. Os valores são fictícios e devem ser inteiros positivos. O primeiro lance deve atingir o mínimo; os seguintes devem superar o maior lance aceito. Em caso de valores iguais, vale a ordem de processamento no servidor.

O organizador inicia o leilão pelo terminal do servidor. O prazo é contado pelo servidor com relógio monotônico. Ao terminar, o servidor rejeita novos lances e apresenta o vencedor e o histórico dos lances aceitos. Se não houver lances aceitos, o resultado indica ausência de vencedor.

## Linguagem e dependências

- **Linguagem:** Python 3.
- **Versão utilizada nos testes:** Python **3.13.1**.
- **Dependências da aplicação:** somente a biblioteca padrão do Python; não é necessário instalar pacotes com `pip`.
- **Wireshark:** ferramenta externa necessária apenas para produzir a captura de tráfego da entrega, não para executar a aplicação.

Os comandos abaixo usam `python`. Se o interpretador estiver disponível como `python3` ou `py`, substitua o comando conforme o ambiente.

## Execução

Execute os comandos na raiz do projeto, em **quatro terminais separados**: um para o servidor e um para cada cliente.

### 1. Iniciar o servidor

```console
python src/server.py
```

O servidor apresenta o item e pergunta:

```text
Deseja iniciar o leilão? (s/n):
```

Aguarde o cadastro dos três clientes antes de responder. O servidor permite iniciar com pelo menos um participante conectado; a demonstração do trabalho deve utilizar pelo menos três.

### 2. Iniciar três clientes no mesmo computador

Em cada terminal, execute um dos comandos:

```console
python src/client.py --servidor 127.0.0.1 --porta-udp 15001
```

```console
python src/client.py --servidor 127.0.0.1 --porta-udp 15002
```

```console
python src/client.py --servidor 127.0.0.1 --porta-udp 15003
```

Informe um nome diferente em cada cliente, por exemplo, `Ana`, `Bruno` e `Celia`. Após o cadastro, cada cliente recebe seu identificador e os dados do item, com a situação `AGUARDANDO`.

O nome não pode ser vazio nem repetir um nome já cadastrado, desconsiderando maiúsculas e minúsculas. O servidor atribui um identificador numérico e associa o participante à conexão TCP; a identificação não depende apenas do IP. O nome permanece reservado até o fim da execução, mesmo após a desconexão.

### 3. Iniciar e usar o leilão

Com os participantes cadastrados, digite `s` no terminal do servidor. Digitar `n` cancela o leilão e encerra o servidor.

Cada cliente oferece o menu:

```text
1) Dar lance  2) Consultar situação  3) Consultar resultado  q) Sair
```

| Opção | Ação |
| --- | --- |
| `1` | Solicita um valor inteiro positivo e envia o lance ao servidor. |
| `2` | Consulta item, mínimo, maior lance, líder, situação e tempo restante. |
| `3` | Consulta vencedor e histórico após o encerramento. Antes disso, recebe uma rejeição. |
| `q` | Encerra o cliente sem interromper os demais participantes. |

O menu aguarda a resposta TCP da operação antes de reaparecer. Avisos UDP e mensagens de início ou encerramento podem aparecer enquanto o usuário digita.

Após 60 segundos, o resultado é enviado por TCP aos clientes conectados e um aviso de encerramento é enviado por UDP. O servidor continua disponível para consultas dos clientes já cadastrados. Para uma nova rodada, encerre os clientes com `q`, finalize o servidor com `Ctrl+C` e execute os programas novamente.

## Endereços, portas e configuração

| Uso | Endereço ou porta padrão | Configuração |
| --- | --- | --- |
| Escuta do servidor | `0.0.0.0` — todas as interfaces IPv4 locais | Constante `HOST` em `src/server.py`. |
| TCP do servidor | `12346` | Constante `PORTA_TCP` nos dois programas. |
| Origem dos avisos UDP do servidor | `12347` | Constante `PORTA_UDP` em `src/server.py`. |
| Servidor acessado pelo cliente | `127.0.0.1` | Argumento `--servidor`, opcional. |
| Recepção UDP do cliente | Informada na execução | Argumento obrigatório `--porta-udp`, entre `1` e `65535`. |
| Origem TCP do cliente | Porta efêmera | Escolhida automaticamente pelo sistema operacional. |

No cadastro TCP, cada cliente informa sua porta UDP. O servidor combina essa porta com o IP de origem da conexão TCP para enviar os avisos. No mesmo computador, use portas UDP diferentes e disponíveis para cada cliente; evite a porta UDP `12347`, usada pelo servidor.

Para executar em computadores diferentes, mantenha o servidor em uma máquina e informe seu IP da rede local nos clientes. Por exemplo, se o IP do servidor for `192.168.1.10`:

```console
python src/client.py --servidor 192.168.1.10 --porta-udp 15001
```

`0.0.0.0` é o endereço de escuta, não o endereço a informar nos clientes. As máquinas devem conseguir se comunicar pela rede. O firewall deve permitir conexões TCP à porta `12346` do servidor e datagramas UDP destinados às portas escolhidas nos clientes, com origem na porta `12347` do servidor.

O item e o mínimo podem ser alterados nas constantes `ITEM` e `LANCE_MINIMO` de `src/server.py`. A constante `DURACAO` está definida em `60`, conforme o enunciado. Não são necessários arquivos externos de configuração do item.

## Protocolo de aplicação

### Codificação e delimitação

Todas as mensagens são objetos **JSON codificados em UTF-8**, com o campo `tipo` identificando a operação ou resposta.

No TCP, cada objeto ocupa uma única linha e termina com o byte de quebra de linha `\n`. Os programas acumulam bytes até encontrar esse delimitador, preservando o restante para a próxima mensagem. Um `recv()` pode conter parte de uma mensagem ou várias mensagens; ele não define os limites das mensagens.

Nos exemplos abaixo, cada linha JSON deve ser seguida de uma quebra de linha real. No UDP, cada datagrama contém um objeto JSON, também seguido de `\n`; o próprio datagrama delimita a mensagem.

### Mensagens TCP

Todos os campos listados são enviados pelo protocolo atual. `null` representa ausência de líder ou vencedor. Booleanos não são aceitos como valores inteiros de lance ou porta.

| Tipo | Direção | Campos além de `tipo` | Resposta ou finalidade |
| --- | --- | --- | --- |
| `REGISTER` | Cliente → servidor | `nome`: string; `porta_udp`: inteiro | Recebe `REGISTER_OK` e depois `LEILAO_INFO`, ou `REGISTER_ERROR`. |
| `REGISTER_OK` | Servidor → cliente | `id`: inteiro; `mensagem`: string | Confirma o cadastro. |
| `REGISTER_ERROR` | Servidor → cliente | `mensagem`: string | Informa nome/porta inválidos, nome repetido, cadastro repetido na conexão ou leilão encerrado. |
| `LEILAO_INFO` | Servidor → cliente | `item`: string; `lance_minimo`: inteiro; `duracao`: inteiro em segundos; `situacao`: string | Apresenta o item após o cadastro e informa o início do leilão. |
| `LANCE` | Cliente → servidor | `valor`: inteiro positivo | Recebe `LANCE_OK` ou `LANCE_ERROR`. |
| `LANCE_OK` | Servidor → cliente | `mensagem`: string; `valor`: inteiro | Confirma a aceitação do lance. |
| `LANCE_ERROR` | Servidor → cliente | `mensagem`: string | Explica a rejeição: prazo, leilão não iniciado, valor inválido, abaixo do mínimo ou sem superar o maior lance. |
| `CONSULTAR` | Cliente → servidor | Nenhum | Recebe `SITUACAO`. |
| `SITUACAO` | Servidor → cliente | `item`: string; `lance_minimo`, `maior_lance`, `tempo_restante`: inteiros; `nome_lider`: string ou null; `situacao`: string | Retorna o estado oficial; tempo em segundos. |
| `RESULTADO` | Cliente → servidor | Nenhum | Recebe `LEILAO_RESULTADO` ou `RESULTADO_ERROR`. |
| `LEILAO_RESULTADO` | Servidor → cliente | `vencedor`: string ou null; `maior_lance`: inteiro; `historico`: lista de objetos com `participante` string e `valor` inteiro | Enviado automaticamente no encerramento e em resposta à consulta posterior. |
| `RESULTADO_ERROR` | Servidor → cliente | `mensagem`: string | Informa que o leilão ainda não foi encerrado. |
| `ERROR` | Servidor → cliente | `mensagem`: string | Indica JSON/UTF-8 inválido, objeto inválido, mensagem excessiva, tipo desconhecido ou operação sem cadastro. |

As situações possíveis são `AGUARDANDO`, `ABERTO` e `ENCERRADO`. Antes de qualquer lance, `maior_lance` é `0` e `nome_lider` é `null`. O histórico contém somente lances aceitos, na ordem de processamento.

#### Exemplo de cadastro e apresentação

Cliente → servidor:

```json
{"tipo":"REGISTER","nome":"Ana","porta_udp":15001}
```

Servidor → cliente, em duas mensagens TCP:

```json
{"tipo":"REGISTER_OK","id":1,"mensagem":"Cadastro realizado com sucesso"}
{"tipo":"LEILAO_INFO","item":"Notebook","lance_minimo":500,"duracao":60,"situacao":"AGUARDANDO"}
```

Ao iniciar, o servidor envia aos participantes:

```json
{"tipo":"LEILAO_INFO","item":"Notebook","lance_minimo":500,"duracao":60,"situacao":"ABERTO"}
```

#### Exemplos de lance aceito e rejeitado

Primeiro lance, enviado por Ana durante o leilão:

```json
{"tipo":"LANCE","valor":500}
```

Resposta:

```json
{"tipo":"LANCE_OK","mensagem":"Lance registrado com sucesso","valor":500}
```

Repetir o valor `500` nesse estado gera:

```json
{"tipo":"LANCE_ERROR","mensagem":"Lance deve superar o maior lance atual"}
```

#### Exemplo de consulta

Cliente → servidor:

```json
{"tipo":"CONSULTAR"}
```

Exemplo de resposta após um lance de Bruno no valor de `600`:

```json
{"tipo":"SITUACAO","item":"Notebook","lance_minimo":500,"maior_lance":600,"nome_lider":"Bruno","tempo_restante":42,"situacao":"ABERTO"}
```

#### Exemplos de resultado

Cliente → servidor:

```json
{"tipo":"RESULTADO"}
```

Antes do encerramento:

```json
{"tipo":"RESULTADO_ERROR","mensagem":"O leilão ainda não foi encerrado"}
```

Após o encerramento, considerando os lances aceitos de Ana e Bruno:

```json
{"tipo":"LEILAO_RESULTADO","vencedor":"Bruno","maior_lance":600,"historico":[{"participante":"Ana","valor":500},{"participante":"Bruno","valor":600}]}
```

Se nenhum lance foi aceito:

```json
{"tipo":"LEILAO_RESULTADO","vencedor":null,"maior_lance":0,"historico":[]}
```

### Avisos UDP

| Tipo | Campos além de `tipo` | Finalidade |
| --- | --- | --- |
| `LEILAO_AVISO` | `atualizacao`: inteiro; `maior_lance`: inteiro; `nome_lider`: string ou null | Anuncia um novo maior lance aceito. |
| `LEILAO_ENCERRADO` | `atualizacao`: inteiro; `vencedor`: string ou null; `maior_lance`: inteiro | Anuncia o encerramento. |

`atualizacao` começa em `1` no primeiro evento e é incrementado a cada lance aceito e no encerramento. A mesma atualização é enviada a todos os destinatários daquele evento. Lances rejeitados não geram avisos nem incrementam esse número.

Para a sequência Ana `500`, Bruno `600` e encerramento, cada cliente conectado recebe datagramas como:

```json
{"tipo":"LEILAO_AVISO","atualizacao":1,"maior_lance":500,"nome_lider":"Ana"}
{"tipo":"LEILAO_AVISO","atualizacao":2,"maior_lance":600,"nome_lider":"Bruno"}
{"tipo":"LEILAO_ENCERRADO","atualizacao":3,"vencedor":"Bruno","maior_lance":600}
```

Cada linha acima corresponde a um datagrama separado. Os avisos não confirmam operações. Não há confirmação nem retransmissão UDP; os datagramas podem se perder ou chegar fora de ordem. O cliente exibe o número recebido, mas não reordena os avisos. Use `CONSULTAR` ou `RESULTADO` por TCP para obter a informação oficial.

## Concorrência, limites e falhas

O servidor utiliza uma thread de atendimento por conexão TCP. Um lock protege participantes, maior lance, histórico e transições de estado, evitando que dois lances de mesmo valor sejam aceitos simultaneamente. Cada conexão também tem um lock de envio para impedir a mistura de mensagens TCP produzidas por threads diferentes.

O controle do prazo e a distribuição UDP utilizam threads próprias. Uma fila preserva a ordem de geração dos avisos UDP. As mensagens TCP de início e resultado são distribuídas em threads independentes por destinatário, para que um cliente lento não atrase os demais.

| Limite | Comportamento |
| --- | --- |
| Solicitação TCP ao servidor | Máximo de `65.536` bytes por mensagem, sem `\n`; excesso gera erro e encerramento da conexão afetada. |
| Resposta TCP recebida pelo cliente | Máximo de `1.048.576` bytes por mensagem, sem `\n`; excesso encerra o atendimento TCP no cliente. |
| Envio TCP pelo servidor | Timeout de `1` segundo para `sendall` e de até `1` segundo para adquirir o lock de envio; falha interrompe a conexão afetada. |
| Leitura TCP no servidor | Timeout de `1` segundo por espera, sem desconectar participantes apenas por ociosidade. |

JSON/UTF-8 inválidos e operações inválidas são tratados pelo servidor. O cliente valida a estrutura das mensagens recebidas e descarta mensagens malformadas durante o recebimento contínuo. A desconexão de um participante não apaga seus lances aceitos nem impede os demais de participar; um participante desconectado pode continuar sendo o vencedor.

## Logs

Os arquivos são criados automaticamente na pasta `logs/`, relativa à raiz do projeto, mesmo que o programa seja iniciado a partir de outro diretório:

- `logs/server.log`: conexões, mensagens TCP/UDP, cadastros, lances, início, encerramento e desconexões.
- `logs/cliente-15001.log`, `logs/cliente-15002.log` e `logs/cliente-15003.log`: exemplos de logs dos clientes, identificados pela porta UDP escolhida.

As entradas registram horário, nível e evento; os registros de mensagens incluem protocolo, direção, origem/destino e tipo. O servidor também registra mudanças importantes de estado.

Os logs são acrescentados aos arquivos existentes entre execuções. Para preservar a evidência de uma sessão específica, copie os arquivos ao final e, com os programas encerrados, mova os logs antigos antes de uma nova sessão.

## Roteiro de demonstração e captura

1. Inicie o servidor e três clientes com nomes e portas UDP diferentes.
2. Consulte a situação antes do início e confira item, mínimo e duração.
3. Digite `s` no servidor e envie, em sequência, os lances `500`, `600` e `700` em clientes diferentes.
4. Tente repetir `700` e oferecer `650`: ambos devem ser rejeitados. Digite `abc` como lance para demonstrar validação local de entrada.
5. Consulte a situação e confira o líder. Saia de um cliente com `q` e continue consultando pelos demais.
6. Aguarde o prazo de 60 segundos, consulte o resultado e tente um lance posterior. Confira vencedor, histórico e rejeição por encerramento.
7. Em outra execução, inicie o leilão sem oferecer lances para verificar o resultado sem vencedor.

Para obter a captura da entrega, inicie o Wireshark antes dos programas, selecione a interface da rede utilizada ou a interface de loopback para `127.0.0.1` e capture a sessão. Use o filtro de exibição:

```text
tcp.port == 12346 || udp.port == 12347
```

Localize uma solicitação/resposta TCP e um aviso UDP pelos exemplos do protocolo. Salve a captura em `.pcapng` ou `.pcap` na pasta `evidence/`. A captura e o relatório de testes de até duas páginas devem ser produzidos separadamente para a entrega; este README não os substitui.

## Limitações

Há uma sala e um item por execução. Não há autenticação real, pagamento, saldo, banco de dados, persistência do estado, reconexão automática ou recuperação após reinício do servidor. A aplicação foi pensada para rede local ou loopback. Históricos que ultrapassem o limite de mensagem do cliente não são paginados.
