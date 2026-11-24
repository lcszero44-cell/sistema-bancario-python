"""Motor financeiro Core Banking com precisão Decimal e Livro-Razão (Ledger) imutável.

Responsabilidades:
- Garantir aritmética monetária exata com ``decimal.Decimal`` e ``ROUND_HALF_UP``.
- Registrar todas as movimentações em um Ledger imutável (``TransactionRecord``)
  com protocolo único de auditoria (UUID4 curto de 8 caracteres) e trilha de saldo
  anterior/posterior.
- Aplicar regras estritas de compliance bancário: bloqueio de valores inválidos,
  teto de saque por transação (R$ 500,00), cota de 3 saques diários com reset
  automático na virada do dia e checagem rigorosa de saldo antes do débito.
- Emitir extratos bancários auditáveis com formatação monetária brasileira.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Callable, Union

from src.domain.exceptions import (
    LimiteDiarioAtingidoError,
    LimiteSaqueExcedidoError,
    SaldoInsuficienteError,
    ValorInvalidoError,
)

MonetaryInput = Union[Decimal, int, str, float]

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")
LIMITE_SAQUE_PADRAO = Decimal("500.00")
LIMITE_SAQUES_DIARIOS_PADRAO = 3

_PADRAO_MILHAR_BR = re.compile(r"^[+-]?[1-9]\d{0,2}(\.\d{3})+(,\d+|(\.\d{3})+)$")
_PADRAO_DECIMAL_BR = re.compile(r"^[+-]?\d+,\d+$")
_PADRAO_NUMERICO_ISO = re.compile(r"^[+-]?\d+(\.\d+)?$")


class TransactionType(str, Enum):
    """Tipos oficiais de lançamento suportados pelo Livro-Razão."""

    DEPOSITO = "DEPÓSITO"
    SAQUE = "SAQUE"


def formatar_moeda_brl(valor: Decimal) -> str:
    """Formata um ``Decimal`` no padrão monetário brasileiro (ex.: ``R$ 1.250,00``)."""
    quantizado = valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    sinal = "-" if quantizado < ZERO else ""
    absoluto = abs(quantizado)
    formatado = f"{absoluto:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{sinal}R$ {formatado}"


def _interpretar_string_monetaria(texto: str) -> str:
    """Normaliza representações textuais brasileiras e internacionais para Decimal."""
    limpo = texto.strip()
    if limpo.upper().startswith("R$"):
        limpo = limpo[2:].strip()

    if not limpo:
        raise ValorInvalidoError("Informe um valor numérico positivo.")

    if _PADRAO_MILHAR_BR.match(limpo):
        return limpo.replace(".", "").replace(",", ".")

    if _PADRAO_DECIMAL_BR.match(limpo):
        return limpo.replace(",", ".")

    if _PADRAO_NUMERICO_ISO.match(limpo):
        return limpo

    raise ValorInvalidoError(
        f"Formato monetário inválido: '{texto}'. Use formatos como 150,00 ou 150.00."
    )


def normalizar_valor_monetario(valor: MonetaryInput) -> Decimal:
    """Valida e converte um valor de entrada para ``Decimal`` positivo com 2 casas decimais.

    Utiliza arredondamento financeiro ``ROUND_HALF_UP`` e rejeita valores booleanos,
    não numéricos, ``NaN``, ``Infinity`` e quantias menores ou iguais a zero.
    """
    if isinstance(valor, bool):
        raise ValorInvalidoError("Valores booleanos não são aceitos em operações financeiras.")

    try:
        if isinstance(valor, Decimal):
            bruto = valor
        elif isinstance(valor, int):
            bruto = Decimal(valor)
        elif isinstance(valor, float):
            bruto = Decimal(str(valor))
        elif isinstance(valor, str):
            bruto = Decimal(_interpretar_string_monetaria(valor))
        else:
            raise ValorInvalidoError(
                f"Tipo de dado não suportado para valor monetário: {type(valor).__name__}."
            )
    except InvalidOperation as exc:
        raise ValorInvalidoError(f"Valor numérico inválido: '{valor}'.") from exc

    if not bruto.is_finite():
        raise ValorInvalidoError("Valores infinitos ou indefinidos (NaN) não são permitidos.")

    if bruto <= ZERO:
        raise ValorInvalidoError("O valor da operação deve ser estritamente maior que R$ 0,00.")

    normalizado = bruto.quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if normalizado <= ZERO:
        raise ValorInvalidoError(
            "O valor informado é inferior à unidade monetária mínima (R$ 0,01)."
        )

    return normalizado


@dataclass(frozen=True)
class TransactionRecord:
    """Registro imutável de auditoria no Livro-Razão (Ledger) bancário."""

    id: str
    timestamp: datetime
    tipo: TransactionType
    valor: Decimal
    saldo_anterior: Decimal
    saldo_posterior: Decimal

    @property
    def timestamp_iso(self) -> str:
        """Retorna carimbo de data/hora no padrão ISO 8601."""
        return self.timestamp.isoformat(timespec="seconds")

    @property
    def timestamp_br(self) -> str:
        """Retorna carimbo de data/hora no padrão brasileiro (DD/MM/AAAA HH:MM:SS)."""
        return self.timestamp.strftime("%d/%m/%Y %H:%M:%S")


@dataclass(frozen=True)
class StatementSummary:
    """Fotografia estruturada e imutável do extrato bancário para auditoria e integrações."""

    titular: str
    agencia: str
    numero_conta: str
    emitido_em: datetime
    transacoes: tuple[TransactionRecord, ...]
    total_entradas: Decimal
    total_saidas: Decimal
    saldo_atual: Decimal
    saques_realizados_hoje: int
    limite_saques_diarios: int
    limite_por_saque: Decimal


class CoreBankingLedger:
    """Motor transacional de conta bancária com Ledger imutável e compliance integrado."""

    def __init__(
        self,
        titular: str = "Cliente Santander DIO",
        agencia: str = "0001",
        numero_conta: str = "00012345-6",
        limite_por_saque: Decimal = LIMITE_SAQUE_PADRAO,
        limite_saques_diarios: int = LIMITE_SAQUES_DIARIOS_PADRAO,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._titular = titular.strip() or "Cliente Santander DIO"
        self._agencia = agencia.strip() or "0001"
        self._numero_conta = numero_conta.strip() or "00012345-6"
        self._limite_por_saque = normalizar_valor_monetario(limite_por_saque)

        if isinstance(limite_saques_diarios, bool) or not isinstance(limite_saques_diarios, int):
            raise ValorInvalidoError("O limite diário de saques deve ser um inteiro positivo.")
        if limite_saques_diarios <= 0:
            raise ValorInvalidoError("O limite diário de saques deve ser maior que zero.")

        self._limite_saques_diarios = limite_saques_diarios
        self._clock: Callable[[], datetime] = clock or datetime.now
        self._saldo: Decimal = ZERO
        self._ledger: list[TransactionRecord] = []

    @property
    def titular(self) -> str:
        return self._titular

    @property
    def agencia(self) -> str:
        return self._agencia

    @property
    def numero_conta(self) -> str:
        return self._numero_conta

    @property
    def saldo(self) -> Decimal:
        """Retorna o saldo consolidado atual com precisão exata de centavos."""
        return self._saldo

    @property
    def historico(self) -> tuple[TransactionRecord, ...]:
        """Retorna uma tupla imutável com todos os lançamentos do Livro-Razão."""
        return tuple(self._ledger)

    @property
    def limite_por_saque(self) -> Decimal:
        return self._limite_por_saque

    @property
    def limite_saques_diarios(self) -> int:
        return self._limite_saques_diarios

    @property
    def saques_realizados_hoje(self) -> int:
        """Conta saques efetuados na data corrente, resetando automaticamente à meia-noite."""
        hoje = self._agora().date()
        return sum(
            1
            for registro in self._ledger
            if registro.tipo is TransactionType.SAQUE and registro.timestamp.date() == hoje
        )

    @property
    def saques_restantes_hoje(self) -> int:
        """Quantidade de saques ainda disponíveis no dia corrente."""
        return max(0, self._limite_saques_diarios - self.saques_realizados_hoje)

    def _agora(self) -> datetime:
        return self._clock()

    @staticmethod
    def _gerar_protocolo() -> str:
        """Gera identificador único curto de auditoria (8 caracteres hexadecimais de UUID4)."""
        return uuid.uuid4().hex[:8].upper()

    def depositar(self, valor: MonetaryInput) -> TransactionRecord:
        """Credita valor positivo na conta e registra o lançamento imutável no Ledger."""
        valor_normalizado = normalizar_valor_monetario(valor)
        saldo_anterior = self._saldo
        saldo_posterior = (saldo_anterior + valor_normalizado).quantize(
            CENTAVO, rounding=ROUND_HALF_UP
        )

        registro = TransactionRecord(
            id=self._gerar_protocolo(),
            timestamp=self._agora(),
            tipo=TransactionType.DEPOSITO,
            valor=valor_normalizado,
            saldo_anterior=saldo_anterior,
            saldo_posterior=saldo_posterior,
        )
        self._saldo = saldo_posterior
        self._ledger.append(registro)
        return registro

    def sacar(self, valor: MonetaryInput) -> TransactionRecord:
        """Valida regras de compliance e debita valor da conta registrando no Ledger.

        Ordem de validação bancária:
        1. Integridade do valor monetário (> R$ 0,00).
        2. Limite operacional diário de saques (máximo 3/dia, reset automático por data).
        3. Limite de valor por transação (máximo R$ 500,00).
        4. Verificação estrita de saldo disponível antes do débito.
        """
        valor_normalizado = normalizar_valor_monetario(valor)

        saques_hoje = self.saques_realizados_hoje
        if saques_hoje >= self._limite_saques_diarios:
            raise LimiteDiarioAtingidoError(
                saques_realizados=saques_hoje,
                limite_diario=self._limite_saques_diarios,
            )

        if valor_normalizado > self._limite_por_saque:
            raise LimiteSaqueExcedidoError(
                valor_solicitado=valor_normalizado,
                limite_transacao=self._limite_por_saque,
            )

        if valor_normalizado > self._saldo:
            raise SaldoInsuficienteError(
                saldo_disponivel=self._saldo,
                valor_solicitado=valor_normalizado,
            )

        saldo_anterior = self._saldo
        saldo_posterior = (saldo_anterior - valor_normalizado).quantize(
            CENTAVO, rounding=ROUND_HALF_UP
        )

        registro = TransactionRecord(
            id=self._gerar_protocolo(),
            timestamp=self._agora(),
            tipo=TransactionType.SAQUE,
            valor=valor_normalizado,
            saldo_anterior=saldo_anterior,
            saldo_posterior=saldo_posterior,
        )
        self._saldo = saldo_posterior
        self._ledger.append(registro)
        return registro

    def obter_resumo_extrato(self) -> StatementSummary:
        """Consolida totais de entradas, saídas e estado atual da conta."""
        total_entradas = sum(
            (r.valor for r in self._ledger if r.tipo is TransactionType.DEPOSITO),
            start=ZERO,
        ).quantize(CENTAVO, rounding=ROUND_HALF_UP)

        total_saidas = sum(
            (r.valor for r in self._ledger if r.tipo is TransactionType.SAQUE),
            start=ZERO,
        ).quantize(CENTAVO, rounding=ROUND_HALF_UP)

        return StatementSummary(
            titular=self._titular,
            agencia=self._agencia,
            numero_conta=self._numero_conta,
            emitido_em=self._agora(),
            transacoes=self.historico,
            total_entradas=total_entradas,
            total_saidas=total_saidas,
            saldo_atual=self._saldo,
            saques_realizados_hoje=self.saques_realizados_hoje,
            limite_saques_diarios=self._limite_saques_diarios,
            limite_por_saque=self._limite_por_saque,
        )

    def gerar_extrato(self) -> str:
        """Emite o extrato bancário institucional auditável formatado em padrão BRL."""
        resumo = self.obter_resumo_extrato()
        largura = 78
        linha_dupla = "═" * (largura - 2)
        linha_simples = "─" * (largura - 2)

        def linha_caixa(texto: str) -> str:
            return f"║ {texto:<{largura - 4}} ║"

        emissao_br = resumo.emitido_em.strftime("%d/%m/%Y %H:%M:%S")
        emissao_iso = resumo.emitido_em.isoformat(timespec="seconds")

        linhas: list[str] = [
            f"╔{linha_dupla}╗",
            f"║{'EXTRATO BANCÁRIO AUDITÁVEL — CORE BANKING LEDGER':^{largura - 2}}║",
            f"╠{linha_dupla}╣",
            linha_caixa(
                f"Titular: {resumo.titular} | Ag: {resumo.agencia} | Conta: {resumo.numero_conta}"
            ),
            linha_caixa(f"Emissão: {emissao_br} ({emissao_iso})"),
            f"╠{linha_simples}╣",
            linha_caixa(
                f"{'PROTOCOLO':<10} {'DATA/HORA':<19} {'OPERAÇÃO':<10} {'VALOR':>14} {'SALDO PÓS':>16}"
            ),
            f"╟{linha_simples}╢",
        ]

        if not resumo.transacoes:
            linhas.append(
                linha_caixa("Nenhuma movimentação financeira registrada até o momento.")
            )
        else:
            for reg in resumo.transacoes:
                sinal = "+" if reg.tipo is TransactionType.DEPOSITO else "-"
                valor_fmt = f"{sinal}{formatar_moeda_brl(reg.valor)}"
                saldo_fmt = formatar_moeda_brl(reg.saldo_posterior)
                linhas.append(
                    linha_caixa(
                        f"{reg.id:<10} {reg.timestamp_br:<19} {reg.tipo.value:<10} "
                        f"{valor_fmt:>14} {saldo_fmt:>16}"
                    )
                )

        linhas.extend(
            [
                f"╠{linha_simples}╣",
                linha_caixa(
                    f"Total de Entradas (Depósitos): {formatar_moeda_brl(resumo.total_entradas)}"
                ),
                linha_caixa(
                    f"Total de Saídas (Saques):      {formatar_moeda_brl(resumo.total_saidas)}"
                ),
                linha_caixa(
                    f"Cota Diária de Saques:         "
                    f"{resumo.saques_realizados_hoje}/{resumo.limite_saques_diarios} "
                    f"(Limite/transação: {formatar_moeda_brl(resumo.limite_por_saque)})"
                ),
                f"╠{linha_dupla}╣",
                linha_caixa(
                    f"SALDO CONSOLIDADO ATUAL:       {formatar_moeda_brl(resumo.saldo_atual)}"
                ),
                f"╚{linha_dupla}╝",
            ]
        )

        return "\n".join(linhas)
