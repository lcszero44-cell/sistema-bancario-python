"""Interface de terminal (CLI) corporativa e resiliente para o Core Banking.

Totalmente desacoplada das regras de negócio: toda validação financeira,
controle de limites e registro contábil é delegado ao ``CoreBankingLedger``.
"""

from __future__ import annotations

import sys
from typing import Callable

from src.domain.exceptions import BankDomainError
from src.domain.ledger import (
    CoreBankingLedger,
    TransactionRecord,
    formatar_moeda_brl,
)


def _configurar_utf8_console() -> None:
    """Garante renderização correta de acentos e box-drawing no terminal Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except OSError:
                pass


class BankingCLI:
    """Controlador interativo de terminal para operações bancárias."""

    LARGURA = 78

    def __init__(
        self,
        ledger: CoreBankingLedger | None = None,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self._ledger = ledger or CoreBankingLedger()
        self._input = input_fn
        self._output = output_fn

    def _linha_caixa(self, texto: str) -> str:
        largura_interna = self.LARGURA - 4
        return f"║ {texto:<{largura_interna}} ║"

    def _exibir_cabecalho(self) -> None:
        borda = "═" * (self.LARGURA - 2)
        titulo = "CORE BANKING SYSTEM — SANTANDER DIO 2025"
        subtitulo = "Motor Financeiro Decimal • Ledger Imutável • Compliance Bancário"
        self._output("")
        self._output(f"╔{borda}╗")
        self._output(f"║{titulo:^{self.LARGURA - 2}}║")
        self._output(f"║{subtitulo:^{self.LARGURA - 2}}║")
        self._output(f"╠{borda}╣")
        self._output(
            self._linha_caixa(
                f"Titular: {self._ledger.titular} | "
                f"Ag: {self._ledger.agencia} | Conta: {self._ledger.numero_conta}"
            )
        )
        self._output(f"╚{borda}╝")

    def _exibir_menu(self) -> None:
        borda_sup = "─" * (self.LARGURA - 2)
        self._output("")
        self._output(f"┌{borda_sup}┐")
        self._output(f"│ {'PAINEL DE OPERAÇÕES BANCÁRIAS':<{self.LARGURA - 4}} │")
        self._output(f"├{borda_sup}┤")
        self._output(f"│ {'[1] ou [D]  Depositar':<{self.LARGURA - 4}} │")
        self._output(f"│ {'[2] ou [S]  Sacar':<{self.LARGURA - 4}} │")
        self._output(f"│ {'[3] ou [E]  Emitir Extrato Auditável':<{self.LARGURA - 4}} │")
        self._output(f"│ {'[4] ou [C]  Consultar Saldo e Limites':<{self.LARGURA - 4}} │")
        self._output(f"│ {'[0] ou [Q]  Encerrar Sessão':<{self.LARGURA - 4}} │")
        self._output(f"└{borda_sup}┘")

    def _exibir_comprovante(self, registro: TransactionRecord) -> None:
        borda = "─" * (self.LARGURA - 2)
        self._output("")
        self._output(f"┌{borda}┐")
        self._output(
            f"│ {'[OK] OPERAÇÃO PROCESSADA E REGISTRADA NO LEDGER':<{self.LARGURA - 4}} │"
        )
        self._output(f"├{borda}┤")
        self._output(f"│ {'Protocolo de Auditoria: ' + registro.id:<{self.LARGURA - 4}} │")
        self._output(
            f"│ {'Data/Hora:              ' + registro.timestamp_br + ' (' + registro.timestamp_iso + ')':<{self.LARGURA - 4}} │"
        )
        self._output(f"│ {'Tipo de Operação:       ' + registro.tipo.value:<{self.LARGURA - 4}} │")
        self._output(
            f"│ {'Valor Movimentado:      ' + formatar_moeda_brl(registro.valor):<{self.LARGURA - 4}} │"
        )
        self._output(
            f"│ {'Saldo Anterior:         ' + formatar_moeda_brl(registro.saldo_anterior):<{self.LARGURA - 4}} │"
        )
        self._output(
            f"│ {'Saldo Atualizado:       ' + formatar_moeda_brl(registro.saldo_posterior):<{self.LARGURA - 4}} │"
        )
        self._output(f"└{borda}┘")

    def _exibir_alerta(self, titulo: str, mensagem: str) -> None:
        borda = "─" * (self.LARGURA - 2)
        self._output("")
        self._output(f"┌{borda}┐")
        self._output(f"│ {f'[ALERTA] {titulo}':<{self.LARGURA - 4}} │")
        self._output(f"├{borda}┤")
        for linha in self._quebrar_texto(mensagem, self.LARGURA - 4):
            self._output(f"│ {linha:<{self.LARGURA - 4}} │")
        self._output(f"└{borda}┘")

    @staticmethod
    def _quebrar_texto(texto: str, limite: int) -> list[str]:
        """Quebra mensagens longas em linhas ajustadas à largura da caixa."""
        palavras = texto.split()
        if not palavras:
            return [""]

        linhas: list[str] = []
        atual = palavras[0]
        for palavra in palavras[1:]:
            if len(atual) + 1 + len(palavra) <= limite:
                atual = f"{atual} {palavra}"
            else:
                linhas.append(atual)
                atual = palavra
        linhas.append(atual)
        return linhas

    def _fluxo_deposito(self) -> None:
        entrada = self._input("Informe o valor para depósito (ex.: 250,00): ")
        try:
            registro = self._ledger.depositar(entrada)
            self._exibir_comprovante(registro)
        except BankDomainError as erro:
            self._exibir_alerta(f"OPERAÇÃO BLOQUEADA ({erro.codigo})", str(erro))

    def _fluxo_saque(self) -> None:
        entrada = self._input("Informe o valor para saque (ex.: 150,00): ")
        try:
            registro = self._ledger.sacar(entrada)
            self._exibir_comprovante(registro)
        except BankDomainError as erro:
            self._exibir_alerta(f"COMPLIANCE / BLOQUEIO ({erro.codigo})", str(erro))

    def _fluxo_extrato(self) -> None:
        self._output("")
        self._output(self._ledger.gerar_extrato())

    def _fluxo_saldo_limites(self) -> None:
        borda = "─" * (self.LARGURA - 2)
        self._output("")
        self._output(f"┌{borda}┐")
        self._output(f"│ {'POSIÇÃO CONSOLIDADA E LIMITES OPERACIONAIS':<{self.LARGURA - 4}} │")
        self._output(f"├{borda}┤")
        self._output(
            f"│ {'Saldo Disponível:       ' + formatar_moeda_brl(self._ledger.saldo):<{self.LARGURA - 4}} │"
        )
        self._output(
            f"│ {'Limite por Saque:       ' + formatar_moeda_brl(self._ledger.limite_por_saque):<{self.LARGURA - 4}} │"
        )
        self._output(
            f"│ {'Saques Realizados Hoje: ' + f'{self._ledger.saques_realizados_hoje}/{self._ledger.limite_saques_diarios}':<{self.LARGURA - 4}} │"
        )
        self._output(
            f"│ {'Saques Restantes Hoje:  ' + str(self._ledger.saques_restantes_hoje):<{self.LARGURA - 4}} │"
        )
        self._output(f"└{borda}┘")

    def executar(self) -> None:
        """Executa o loop principal do terminal bancário de forma resiliente."""
        _configurar_utf8_console()
        self._exibir_cabecalho()

        while True:
            self._exibir_menu()
            try:
                opcao = self._input("\nSelecione uma opção => ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                self._output("\nSessão bancária encerrada com segurança.")
                break

            if opcao in {"1", "d", "depositar", "depósito", "deposito"}:
                try:
                    self._fluxo_deposito()
                except (EOFError, KeyboardInterrupt):
                    self._output("\nOperação cancelada. Sessão encerrada com segurança.")
                    break
            elif opcao in {"2", "s", "sacar", "saque"}:
                try:
                    self._fluxo_saque()
                except (EOFError, KeyboardInterrupt):
                    self._output("\nOperação cancelada. Sessão encerrada com segurança.")
                    break
            elif opcao in {"3", "e", "extrato"}:
                self._fluxo_extrato()
            elif opcao in {"4", "c", "consulta", "saldo"}:
                self._fluxo_saldo_limites()
            elif opcao in {"0", "q", "sair", "exit"}:
                self._output(
                    "\nSessão bancária encerrada com segurança. Obrigado por utilizar o Core Banking."
                )
                break
            else:
                self._exibir_alerta(
                    "OPÇÃO INVÁLIDA",
                    "Comando não reconhecido. Escolha 1 (Depositar), 2 (Sacar), "
                    "3 (Extrato), 4 (Saldo/Limites) ou 0 (Sair).",
                )
