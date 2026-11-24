"""Suíte de testes unitários para o motor financeiro Core Banking e CLI.

Valida precisão monetária Decimal (ROUND_HALF_UP), regras de compliance bancário,
imutabilidade do Livro-Razão (Ledger), reset automático de limite diário na virada
do dia, consistência do extrato auditável e resiliência da interface CLI.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta
from decimal import Decimal

from src.domain.exceptions import (
    LimiteDiarioAtingidoError,
    LimiteSaqueExcedidoError,
    SaldoInsuficienteError,
    ValorInvalidoError,
)
from src.domain.ledger import (
    CoreBankingLedger,
    TransactionType,
    formatar_moeda_brl,
    normalizar_valor_monetario,
)
from src.ui.cli import BankingCLI


class FakeClock:
    """Relógio determinístico para testes de timestamp e virada de dia."""

    def __init__(self, momento_inicial: datetime) -> None:
        self._atual = momento_inicial

    def __call__(self) -> datetime:
        return self._atual

    def avancar(self, **kwargs: int) -> None:
        self._atual += timedelta(**kwargs)


class TestPrecisaoMonetariaEFormatacao(unittest.TestCase):
    """Garante integridade financeira com Decimal e padrão monetário BRL."""

    def test_precisao_decimal_evita_erro_ponto_flutuante(self) -> None:
        ledger = CoreBankingLedger()
        ledger.depositar("0.10")
        ledger.depositar("0.20")
        self.assertEqual(ledger.saldo, Decimal("0.30"))

    def test_arredondamento_round_half_up(self) -> None:
        self.assertEqual(normalizar_valor_monetario(Decimal("10.005")), Decimal("10.01"))
        self.assertEqual(normalizar_valor_monetario(Decimal("10.015")), Decimal("10.02"))
        self.assertEqual(normalizar_valor_monetario(Decimal("10.004")), Decimal("10.00"))

    def test_formatacao_moeda_padrao_brasileiro(self) -> None:
        self.assertEqual(formatar_moeda_brl(Decimal("0")), "R$ 0,00")
        self.assertEqual(formatar_moeda_brl(Decimal("1250")), "R$ 1.250,00")
        self.assertEqual(formatar_moeda_brl(Decimal("1234567.89")), "R$ 1.234.567,89")

    def test_aceita_formatos_string_brasileiro_e_internacional(self) -> None:
        self.assertEqual(normalizar_valor_monetario("1.250,50"), Decimal("1250.50"))
        self.assertEqual(normalizar_valor_monetario("R$ 350,75"), Decimal("350.75"))
        self.assertEqual(normalizar_valor_monetario("499.99"), Decimal("499.99"))


class TestDepositoEValidacoes(unittest.TestCase):
    """Testa regras de crédito e bloqueio de valores inválidos."""

    def setUp(self) -> None:
        self.clock = FakeClock(datetime(2025, 8, 15, 10, 30, 0))
        self.ledger = CoreBankingLedger(clock=self.clock)

    def test_deposito_valido_atualiza_saldo_e_gera_protocolo(self) -> None:
        registro = self.ledger.depositar("1.250,00")

        self.assertEqual(self.ledger.saldo, Decimal("1250.00"))
        self.assertEqual(len(self.ledger.historico), 1)
        self.assertEqual(len(registro.id), 8)
        self.assertEqual(registro.tipo, TransactionType.DEPOSITO)
        self.assertEqual(registro.valor, Decimal("1250.00"))
        self.assertEqual(registro.saldo_anterior, Decimal("0.00"))
        self.assertEqual(registro.saldo_posterior, Decimal("1250.00"))
        self.assertEqual(registro.timestamp_br, "15/08/2025 10:30:00")
        self.assertEqual(registro.timestamp_iso, "2025-08-15T10:30:00")

    def test_deposito_negativo_ou_zero_bloqueado(self) -> None:
        valores_invalidos = [0, -1, -0.01, Decimal("0.00"), Decimal("-150.00"), "0", "-50,00"]
        for valor in valores_invalidos:
            with self.subTest(valor=valor):
                with self.assertRaises(ValorInvalidoError) as ctx:
                    self.ledger.depositar(valor)
                self.assertEqual(ctx.exception.codigo, "ERR_VALOR_INVALIDO")

        self.assertEqual(self.ledger.saldo, Decimal("0.00"))
        self.assertEqual(len(self.ledger.historico), 0)

    def test_deposito_nao_numerico_booleano_ou_nao_finito_bloqueado(self) -> None:
        entradas_invalidas = [
            "abc",
            "",
            "10,20,30",
            True,
            False,
            Decimal("NaN"),
            Decimal("Infinity"),
            "0.001",
        ]
        for entrada in entradas_invalidas:
            with self.subTest(entrada=entrada):
                with self.assertRaises(ValorInvalidoError):
                    self.ledger.depositar(entrada)

        self.assertEqual(self.ledger.saldo, Decimal("0.00"))
        self.assertEqual(len(self.ledger.historico), 0)


class TestSaqueEComplianceBancario(unittest.TestCase):
    """Testa saques, teto por transação, saldo insuficiente e cota diária."""

    def setUp(self) -> None:
        self.clock = FakeClock(datetime(2025, 8, 15, 14, 0, 0))
        self.ledger = CoreBankingLedger(clock=self.clock)

    def test_saque_valido_debita_saldo_e_registra_auditoria(self) -> None:
        self.ledger.depositar("1000.00")
        saque = self.ledger.sacar("250,50")

        self.assertEqual(self.ledger.saldo, Decimal("749.50"))
        self.assertEqual(saque.tipo, TransactionType.SAQUE)
        self.assertEqual(saque.valor, Decimal("250.50"))
        self.assertEqual(saque.saldo_anterior, Decimal("1000.00"))
        self.assertEqual(saque.saldo_posterior, Decimal("749.50"))
        self.assertEqual(self.ledger.saques_realizados_hoje, 1)
        self.assertEqual(self.ledger.saques_restantes_hoje, 2)

    def test_saque_no_limite_exato_de_500_permitido(self) -> None:
        self.ledger.depositar("500.00")
        saque = self.ledger.sacar("500.00")
        self.assertEqual(saque.valor, Decimal("500.00"))
        self.assertEqual(self.ledger.saldo, Decimal("0.00"))

    def test_bloqueio_saque_acima_de_500(self) -> None:
        self.ledger.depositar("2000.00")

        with self.assertRaises(LimiteSaqueExcedidoError) as ctx:
            self.ledger.sacar("500.01")

        self.assertEqual(ctx.exception.codigo, "ERR_LIMITE_SAQUE_EXCEDIDO")
        self.assertEqual(ctx.exception.valor_solicitado, Decimal("500.01"))
        self.assertEqual(ctx.exception.limite_transacao, Decimal("500.00"))
        self.assertEqual(self.ledger.saldo, Decimal("2000.00"))
        self.assertEqual(self.ledger.saques_realizados_hoje, 0)

    def test_bloqueio_por_saldo_insuficiente(self) -> None:
        self.ledger.depositar("100.00")

        with self.assertRaises(SaldoInsuficienteError) as ctx:
            self.ledger.sacar("100.01")

        self.assertEqual(ctx.exception.codigo, "ERR_SALDO_INSUFICIENTE")
        self.assertEqual(ctx.exception.saldo_disponivel, Decimal("100.00"))
        self.assertEqual(ctx.exception.valor_solicitado, Decimal("100.01"))
        self.assertEqual(self.ledger.saldo, Decimal("100.00"))
        self.assertEqual(self.ledger.saques_realizados_hoje, 0)

    def test_bloqueio_no_quarto_saque_diario_e_reset_na_virada_do_dia(self) -> None:
        self.ledger.depositar("2000.00")

        self.ledger.sacar("100.00")
        self.ledger.sacar("150.00")
        self.ledger.sacar("200.00")
        self.assertEqual(self.ledger.saques_realizados_hoje, 3)
        self.assertEqual(self.ledger.saques_restantes_hoje, 0)

        with self.assertRaises(LimiteDiarioAtingidoError) as ctx:
            self.ledger.sacar("50.00")

        self.assertEqual(ctx.exception.codigo, "ERR_LIMITE_DIARIO_ATINGIDO")
        self.assertEqual(self.ledger.saldo, Decimal("1550.00"))

        # Avança para o dia seguinte — o limite diário deve resetar automaticamente
        self.clock.avancar(days=1)
        self.assertEqual(self.ledger.saques_realizados_hoje, 0)
        self.assertEqual(self.ledger.saques_restantes_hoje, 3)

        novo_saque = self.ledger.sacar("50.00")
        self.assertEqual(novo_saque.saldo_posterior, Decimal("1500.00"))
        self.assertEqual(self.ledger.saques_realizados_hoje, 1)


class TestLedgerImutabilidadeEExtrato(unittest.TestCase):
    """Valida imutabilidade do Ledger e exatidão do extrato bancário auditável."""

    def setUp(self) -> None:
        self.clock = FakeClock(datetime(2025, 8, 15, 9, 0, 0))
        self.ledger = CoreBankingLedger(
            titular="Maria Silva",
            agencia="0001",
            numero_conta="00998877-1",
            clock=self.clock,
        )

    def test_registro_transacao_imutavel_e_historico_protegido(self) -> None:
        registro = self.ledger.depositar("500.00")

        with self.assertRaises(FrozenInstanceError):
            registro.valor = Decimal("9999.00")  # type: ignore[misc]

        self.assertIsInstance(self.ledger.historico, tuple)

    def test_extrato_sem_movimentacoes(self) -> None:
        extrato = self.ledger.gerar_extrato()
        self.assertIn("EXTRATO BANCÁRIO AUDITÁVEL", extrato)
        self.assertIn("Nenhuma movimentação financeira registrada", extrato)
        self.assertIn("R$ 0,00", extrato)

    def test_consistencia_exata_saldo_resumo_e_extrato(self) -> None:
        dep1 = self.ledger.depositar("1500.00")
        self.clock.avancar(minutes=15)
        saq1 = self.ledger.sacar("250.00")

        resumo = self.ledger.obter_resumo_extrato()
        self.assertEqual(resumo.total_entradas, Decimal("1500.00"))
        self.assertEqual(resumo.total_saidas, Decimal("250.00"))
        self.assertEqual(resumo.saldo_atual, Decimal("1250.00"))
        self.assertEqual(resumo.total_entradas - resumo.total_saidas, resumo.saldo_atual)

        extrato = self.ledger.gerar_extrato()
        self.assertIn("Maria Silva", extrato)
        self.assertIn(dep1.id, extrato)
        self.assertIn(saq1.id, extrato)
        self.assertIn("DEPÓSITO", extrato)
        self.assertIn("SAQUE", extrato)
        self.assertIn("R$ 1.500,00", extrato)
        self.assertIn("R$ 250,00", extrato)
        self.assertIn("R$ 1.250,00", extrato)


class TestResilienciaCLI(unittest.TestCase):
    """Garante que a interface CLI nunca quebra por entradas inválidas do usuário."""

    def test_fluxo_completo_com_entradas_invalidas_e_operacoes_reais(self) -> None:
        entradas = iter(
            [
                "opcao_inexistente",
                "1",
                "texto_invalido",
                "1",
                "1.500,00",
                "2",
                "600,00",
                "2",
                "250,00",
                "4",
                "3",
                "0",
            ]
        )
        saidas: list[str] = []
        ledger = CoreBankingLedger(clock=FakeClock(datetime(2025, 8, 15, 12, 0, 0)))
        cli = BankingCLI(
            ledger=ledger,
            input_fn=lambda _: next(entradas),
            output_fn=saidas.append,
        )

        cli.executar()
        saida_completa = "\n".join(saidas)

        self.assertEqual(ledger.saldo, Decimal("1250.00"))
        self.assertIn("OPÇÃO INVÁLIDA", saida_completa)
        self.assertIn("ERR_VALOR_INVALIDO", saida_completa)
        self.assertIn("ERR_LIMITE_SAQUE_EXCEDIDO", saida_completa)
        self.assertIn("R$ 1.250,00", saida_completa)
        self.assertIn("Sessão bancária encerrada com segurança", saida_completa)


if __name__ == "__main__":
    unittest.main()
