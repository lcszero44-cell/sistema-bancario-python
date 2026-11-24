"""Ponto de entrada (entrypoint) da aplicação Core Banking CLI."""

from __future__ import annotations

from src.domain.ledger import CoreBankingLedger
from src.ui.cli import BankingCLI


def main() -> None:
    """Inicializa o motor financeiro e executa a interface de terminal."""
    ledger = CoreBankingLedger()
    cli = BankingCLI(ledger=ledger)
    cli.executar()


if __name__ == "__main__":
    main()
