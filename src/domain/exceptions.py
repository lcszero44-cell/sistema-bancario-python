"""Exceções de domínio bancário claras, tipadas e rastreáveis.

Cada exceção representa uma violação explícita de regra financeira ou de
compliance operacional, carregando um código padronizado para auditoria e
observabilidade.
"""

from __future__ import annotations

from decimal import Decimal


def _formatar_brl(valor: Decimal) -> str:
    """Formata um valor Decimal no padrão monetário brasileiro (ex.: R$ 1.250,00)."""
    formatado = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatado}"


class BankDomainError(Exception):
    """Exceção base para violações de regras do domínio Core Banking."""

    codigo: str = "ERR_DOMINIO_BANCARIO"

    def __init__(self, mensagem: str, codigo: str | None = None) -> None:
        if codigo is not None:
            self.codigo = codigo
        super().__init__(mensagem)


class ValorInvalidoError(BankDomainError):
    """Lançada quando o valor informado é não numérico, negativo, zero ou inválido."""

    codigo: str = "ERR_VALOR_INVALIDO"

    def __init__(self, mensagem: str = "Valor monetário inválido para a operação.") -> None:
        super().__init__(mensagem, codigo=self.codigo)


class SaldoInsuficienteError(BankDomainError):
    """Lançada quando o saldo disponível é inferior ao valor solicitado para saque."""

    codigo: str = "ERR_SALDO_INSUFICIENTE"

    def __init__(
        self,
        saldo_disponivel: Decimal,
        valor_solicitado: Decimal,
        mensagem: str | None = None,
    ) -> None:
        self.saldo_disponivel = saldo_disponivel
        self.valor_solicitado = valor_solicitado
        texto = mensagem or (
            f"Saldo insuficiente. Disponível: {_formatar_brl(saldo_disponivel)} | "
            f"Solicitado: {_formatar_brl(valor_solicitado)}."
        )
        super().__init__(texto, codigo=self.codigo)


class LimiteSaqueExcedidoError(BankDomainError):
    """Lançada quando um saque ultrapassa o teto permitido por transação."""

    codigo: str = "ERR_LIMITE_SAQUE_EXCEDIDO"

    def __init__(
        self,
        valor_solicitado: Decimal,
        limite_transacao: Decimal,
        mensagem: str | None = None,
    ) -> None:
        self.valor_solicitado = valor_solicitado
        self.limite_transacao = limite_transacao
        texto = mensagem or (
            f"Valor do saque ({_formatar_brl(valor_solicitado)}) excede o limite máximo "
            f"por transação de {_formatar_brl(limite_transacao)}."
        )
        super().__init__(texto, codigo=self.codigo)


class LimiteDiarioAtingidoError(BankDomainError):
    """Lançada quando o limite operacional de saques diários já foi atingido."""

    codigo: str = "ERR_LIMITE_DIARIO_ATINGIDO"

    def __init__(
        self,
        saques_realizados: int,
        limite_diario: int,
        mensagem: str | None = None,
    ) -> None:
        self.saques_realizados = saques_realizados
        self.limite_diario = limite_diario
        texto = mensagem or (
            f"Limite diário de saques atingido ({saques_realizados}/{limite_diario}). "
            "Novos saques serão liberados automaticamente na virada do dia."
        )
        super().__init__(texto, codigo=self.codigo)
