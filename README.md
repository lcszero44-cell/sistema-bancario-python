# 🏦 Core Banking System — Sistema Bancário com Python

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Architecture: Clean / Domain-Driven](https://img.shields.io/badge/Architecture-Clean%20%2F%20Domain--Driven-0A66C2?style=for-the-badge)](#arquitetura-do-sistema)
[![Precision: Decimal Financial Standard](https://img.shields.io/badge/Precision-Decimal%20ROUND__HALF__UP-1E7E34?style=for-the-badge)](#visão-executiva-e-dores-resolvidas)
[![Tests: Passing](https://img.shields.io/badge/Tests-Passing%20(unittest)-2EA44F?style=for-the-badge&logo=checkmarx&logoColor=white)](#execução-da-suíte-de-testes)
[![Bootcamp Santander 2025](https://img.shields.io/badge/DIO-Santander%202025%20Back--End-EC0000?style=for-the-badge)](https://www.dio.me/)

Implementação corporativa de nível **Core Banking** para o desafio **"Criando um Sistema Bancário com Python"** (Bootcamp Santander 2025 — Back-End com Python / DIO). Projetado com **Arquitetura Limpa (Clean Architecture)**, aritmética monetária exata (`decimal.Decimal`), **Livro-Razão (Ledger) imutável** com trilha de auditoria completa e cobertura automatizada de regras de compliance.

---

## Visão Executiva e Dores Resolvidas

Em instituições financeiras reais, scripts monolíticos misturando interface com lógica de saldo geram alto risco operacional, inconsistências contábeis e impossibilidade de auditoria. Esta solução ataca diretamente quatro dores críticas de sistemas financeiros:

| Dor Real em Sistemas Financeiros | Solução Implementada no Core Banking |
| :--- | :--- |
| **Deriva de centavos com `float`** (`0.1 + 0.2 != 0.3`) | Uso exclusivo de `decimal.Decimal` quantizado em `0.01` com arredondamento **`ROUND_HALF_UP`** (padrão contábil/bancário internacional). |
| **Falta de rastreabilidade contábil** | **Ledger (Livro-Razão) imutável** (`@dataclass(frozen=True)`) que registra cada operação com protocolo único `UUID4` (8 chars), carimbo `ISO 8601` / `BR`, valor, saldo anterior e saldo posterior. |
| **Violação de regras de risco e compliance** | Motor transacional valida, antes de qualquer débito: integridade numérica (`> R$ 0,00`), cota de **3 saques diários** com reset automático na virada do dia, teto de **R$ 500,00 por saque** e saldo disponível estrito. |
| **Acoplamento entre regras e canal de atendimento** | Separação rigorosa entre `Domain (Core Banking Ledger)` e `UI (CLI)`, permitindo plugar facilmente uma API REST (FastAPI/Django), mensageria ou banco de dados sem alterar o domínio. |

---

## Arquitetura do Sistema

```text
+-------------------------------------------------------------------------+
|                            ENTRYPOINT (main.py)                         |
|           Inicializa CoreBankingLedger e injeta na camada de UI         |
+------------------------------------+------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                       UI LAYER — src/ui/cli.py                          |
|  - Interface de terminal corporativa com box-drawing characters         |
|  - Tratamento resiliente de entradas inválidas, Ctrl+C e EOF            |
|  - Exibe comprovantes com protocolo e alertas tipados de compliance     |
|  - ZERO regra de negócio financeira (apenas orquestra e apresenta)      |
+------------------------------------+------------------------------------+
                                     | chama depositar(), sacar(),
                                     | gerar_extrato()
                                     v
+-------------------------------------------------------------------------+
|                DOMAIN LAYER — src/domain/ (Core Banking)                |
|                                                                         |
|  +----------------------------------+  +-----------------------------+  |
|  |           ledger.py              |  |        exceptions.py        |  |
|  | - CoreBankingLedger              |  | - BankDomainError (base)    |  |
|  | - TransactionRecord (frozen)     |  | - ValorInvalidoError        |  |
|  | - StatementSummary (frozen)      |  | - SaldoInsuficienteError    |  |
|  | - Decimal + ROUND_HALF_UP        |  | - LimiteSaqueExcedidoError  |  |
|  | - Controle diário por data real  |  | - LimiteDiarioAtingidoError |  |
|  | - Extrato auditável em padrão BR |  |   (com códigos de auditoria)|  |
|  +----------------------------------+  +-----------------------------+  |
+------------------------------------+------------------------------------+
                                     ^
                                     | valida invariantes, compliance
                                     | e virada de dia (FakeClock)
+------------------------------------+------------------------------------+
|                   TESTS LAYER — tests/test_ledger.py                    |
|  - Suíte unitária nativa em unittest (zero dependências externas)       |
|  - Precisão Decimal, bloqueios de risco, imutabilidade e fluxo CLI      |
+-------------------------------------------------------------------------+
```

---

## Estrutura do Projeto

```text
sistema-bancario-python/
├── main.py                      # Ponto de entrada da aplicação CLI
├── README.md                    # Documentação executiva e arquitetural
├── .gitignore                   # Padrão Python
├── src/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── exceptions.py        # Exceções de domínio tipadas e códigos de erro
│   │   └── ledger.py            # Motor financeiro Decimal, compliance e Ledger imutável
│   └── ui/
│       ├── __init__.py
│       └── cli.py               # Terminal interativo resiliente com box-drawing
└── tests/
    ├── __init__.py
    └── test_ledger.py           # Suíte completa de testes unitários (unittest)
```

---

## Regras de Negócio e Compliance Bancário

| Operação / Regra | Política Aplicada | Exceção / Código de Auditoria |
| :--- | :--- | :--- |
| **Depósito** | Aceita apenas valores estritamente positivos (`> R$ 0,00`), em formato BR (`1.250,50`) ou ISO (`1250.50`). | `ValorInvalidoError` (`ERR_VALOR_INVALIDO`) |
| **Teto por Saque** | Limite máximo de **R$ 500,00** por transação individual. | `LimiteSaqueExcedidoError` (`ERR_LIMITE_SAQUE_EXCEDIDO`) |
| **Cota Diária de Saques** | Máximo de **3 saques por dia**, calculado pela data corrente do relógio (reset automático à meia-noite). | `LimiteDiarioAtingidoError` (`ERR_LIMITE_DIARIO_ATINGIDO`) |
| **Verificação de Saldo** | Validação rigorosa de fundos disponíveis antes de efetuar qualquer débito. | `SaldoInsuficienteError` (`ERR_SALDO_INSUFICIENTE`) |
| **Extrato Auditável** | Exibe cabeçalho institucional, emissão (BR/ISO), protocolos `UUID4`, histórico de lançamentos, totais do período e saldo consolidado (`R$ 1.250,00`). | Consistência garantida por `Decimal` e `TransactionRecord` imutável |

---

## Como Executar

### Pré-requisitos
- **Python 3.10+** (utiliza exclusivamente a biblioteca padrão do Python — zero dependências externas).

### Iniciar o Terminal Bancário
```bash
python main.py
```

### Execução da Suíte de Testes
```bash
python -m unittest discover -s tests -v
```

---

## Exemplo de Extrato Bancário Auditável

```text
╔════════════════════════════════════════════════════════════════════════════╗
║              EXTRATO BANCÁRIO AUDITÁVEL — CORE BANKING LEDGER              ║
╠════════════════════════════════════════════════════════════════════════════╣
║ Titular: Cliente Santander DIO | Ag: 0001 | Conta: 00012345-6              ║
║ Emissão: 15/08/2025 14:15:00 (2025-08-15T14:15:00)                         ║
╠────────────────────────────────────────────────────────────────────────────╣
║ PROTOCOLO  DATA/HORA           OPERAÇÃO            VALOR        SALDO PÓS  ║
╟────────────────────────────────────────────────────────────────────────────╢
║ 4F8A1C9E   15/08/2025 14:00:00 DEPÓSITO     +R$ 1.500,00      R$ 1.500,00  ║
║ 9B2E7D10   15/08/2025 14:15:00 SAQUE          -R$ 250,00      R$ 1.250,00  ║
╠────────────────────────────────────────────────────────────────────────────╣
║ Total de Entradas (Depósitos): R$ 1.500,00                                 ║
║ Total de Saídas (Saques):      R$ 250,00                                   ║
║ Cota Diária de Saques:         1/3 (Limite/transação: R$ 500,00)           ║
╠════════════════════════════════════════════════════════════════════════════╣
║ SALDO CONSOLIDADO ATUAL:       R$ 1.250,00                                 ║
╚════════════════════════════════════════════════════════════════════════════╝
```

---

## Autor

Desenvolvido por **Lucas** ([@lcszero44-cell](https://github.com/lcszero44-cell)) como projeto de portfólio para o **Bootcamp Santander 2025 — Back-End com Python (DIO)**.
