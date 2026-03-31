# Demo de Paralelismo GUI

Aplicação didática para demonstrar conceitos de **threads**, **processos**, **mutex** e **comunicação entre processos** com interface gráfica interativa.

---

## Como rodar

```bash
pip install Pillow
python main.py
```

Abre a janela de escolha de modo.

---

## Modos disponíveis

### Modo Threads

Duas ou mais interfaces no mesmo processo (mesmo PID), cada receptor em uma thread própria.

**Layout:** Remetente (esquerda) | Receptores (centro, rolável) | Monitor (direita)

#### Remetente

| Elemento | O que faz |
|---|---|
| Campo de texto | Digita a mensagem a enviar |
| Menu **Destino** | `Broadcast` envia para todos; `Receptor N` envia para um específico |
| **⚡ PARALELO / 🔒 SÍNCRONO** | Alterna o modo de envio (ver abaixo) |
| Botão **Selecionar 📁** | Escolhe arquivo ou imagem para enviar |
| **Enviar Texto →** | Envia a mensagem de texto |
| **Enviar Arquivo →** | Envia o arquivo selecionado |
| Status embaixo | Mostra se está aguardando ACK ou pronto |

#### Modos de envio

**PARALELO (padrão)**
- Cada mensagem enviada ganha uma **thread própria** que aguarda o ACK.
- O remetente fica **livre imediatamente** — você pode continuar enviando.
- As confirmações chegam conforme cada receptor termina de processar.
- Para ver a fila: adicione vários receptores, coloque delay alto (3–5 s), envie várias mensagens seguidas. Observe as barras de fila enchendo e os ACKs chegando de forma assíncrona no log.

**SÍNCRONO**
- O botão **trava** após cada envio.
- Só destrava quando todos os receptores-alvo enviarem ACK.
- Demonstra o custo de esperar por I/O bloqueante.

#### Receptores

Cada receptor é um painel independente com:

| Elemento | O que faz |
|---|---|
| **TID** | Thread ID único — prova que é uma thread diferente |
| Slider **Delay** | Tempo que o receptor "demora" para processar (0,2 s a 5 s) |
| Barra de fila | Fica laranja/vermelha quando há mensagens acumuladas |
| Log interno | Mostra cada mensagem recebida com timestamp e ACK enviado |

Botões da toolbar:
- **+ Adicionar Receptor** — cria novo receptor com thread própria
- **− Remover último** — encerra o receptor e sua thread

#### Monitor (direita)

Mostra em tempo real: estatísticas de envio/ACK, todas as threads ativas do processo (com TIDs), estado de cada fila e descrição do modo atual.

---

### Modo Processos

Dois processos com PIDs distintos comunicando-se via **socket TCP** (localhost).

**Janela Remetente** (abre ao clicar no modo):

| Elemento | O que faz |
|---|---|
| Campo de texto | Mensagem a enviar |
| **Selecionar 📁** | Arquivo ou imagem |
| **Enviar Texto / Arquivo** | Envia via socket (só ativo após conectar) |
| Campo **Porta** | Porta TCP usada (padrão 55555) |
| **▶ Iniciar Receptor** | Lança o processo receptor em nova janela com console próprio |
| **■ Parar Receptor** | Encerra o subprocesso |
| Status do receptor | Mostra PID do processo filho, uptime e estado da conexão |
| **Mutex ON/OFF** | Protege o envio com Lock — sem mutex, envios concorrentes podem se sobrepor |

**Janela Receptor** (processo separado):
- Exibe o próprio PID — diferente do remetente, provando processos distintos
- Mostra cada mensagem recebida
- Imagens são exibidas inline e salvas em `received_files/`
- Log de conexão/desconexão do socket

---

### Demos de Paralelismo

Cinco demonstrações interativas acessíveis pelo botão **🔬 Demos de Paralelismo** no launcher.

#### ⚡ Race Condition

| Elemento | O que faz |
|---|---|
| Radio **Thread / Processo** | Thread usa `threading.Lock`; Processo usa `multiprocessing.Value` + `multiprocessing.Lock` (race real entre núcleos) |
| Spinner **Workers (N)** | Quantas threads/processos competem pelo contador |
| Spinner **Incrementos (M)** | Quantas vezes cada worker incrementa — esperado final = N×M |
| **Mutex ON/OFF** | Ativado: resultado sempre correto. Desativado: race condition, resultado < N×M |
| **▶ Iniciar Demo** | Executa e mostra esperado vs obtido, diferença e tempo |

Dica: use 8+ workers, 500+ incrementos e mutex OFF para ver a diferença claramente.

#### 💀 Deadlock

| Botão | O que faz |
|---|---|
| **Criar Deadlock (sem timeout)** | Thread A pega Lock-1 e aguarda Lock-2; Thread B pega Lock-2 e aguarda Lock-1 → ambas travam para sempre |
| **Criar com Timeout** | Mesmo cenário, mas cada `acquire` tem timeout configurável — detecta e reporta o deadlock sem travar |
| Spinner **Timeout (s)** | Tempo antes de desistir na versão com detecção |

O painel de estado mostra em tempo real qual lock cada thread segura e qual está esperando.

#### 🚦 Semáforo

| Elemento | O que faz |
|---|---|
| Spinner **Slots (N)** | Tamanho do `Semaphore(N)` — quantos workers entram ao mesmo tempo |
| Spinner **Workers (M)** | Total de workers que tentam entrar |
| Spinner **Delay (s)** | Tempo que cada worker fica na seção crítica |
| Grade de workers | 🟢 executando dentro do semáforo · 🟡 aguardando · ⬜ concluído |
| Contador **Ativos** | Nunca ultrapassa N — comprova o controle do semáforo |

#### 🚧 Barreira (Barrier)

| Elemento | O que faz |
|---|---|
| Spinner **Threads (N)** | Quantas threads participam do `Barrier(N)` |
| Grade de threads | 🔵 fase 1 (trabalhando) · ⏸ na barreira · 🟢 fase 2 (avançou) |
| Barra de progresso | Mostra quantas threads já chegaram à barreira |

Cada thread tem delay aleatório na fase 1 — dá para ver threads mais rápidas esperando as mais lentas na barreira antes de todas avançarem juntas.

#### 🏊 Thread Pool

| Botão | O que faz |
|---|---|
| **▶ Rodar com Pool** | `ThreadPoolExecutor(N)` — N threads fixas reutilizadas para M tarefas |
| **▶ Rodar sem Pool** | Cria uma thread nova por tarefa — compare o tempo e os TIDs no log |
| Spinner **Tamanho do pool** | N workers fixos no pool |
| Spinner **Nº de tarefas** | M tarefas a processar |

Os TIDs no log mostram a reutilização de threads no modo pool vs TIDs únicos no modo "nova thread por tarefa".

## Estrutura do código

```
main.py                    # entrada; --receiver <porta> abre o receptor
core/
  ipc.py                   # Message, ThreadQueue, SocketServer, SocketClient
  mutex_manager.py         # Lock + workers de processo (top-level para pickle)
  thread_manager.py        # cria/inspeciona threads
  process_manager.py       # lança subprocesso receptor
gui/
  launcher.py              # janela inicial (3 botões)
  thread_window.py         # modo threads — ReceiverPanel + ThreadWindow
  process_window.py        # modo processos — remetente
  receiver_window.py       # modo processos — receptor (subprocesso)
  demos_window.py          # 5 demos: race condition, deadlock, semáforo, barreira, pool
  styles.py                # paleta de cores e helpers de widget
utils/
  file_utils.py            # base64 encode/decode para arquivos
```

Arquivos recebidos no Modo Processos ficam em `received_files/`.
