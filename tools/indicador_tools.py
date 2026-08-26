"""Tools de leitura usadas pelo especialista de indicadores."""

from tools.ciclo_tools import ciclo_riscos_pendencias, ciclo_visao_geral
from tools.predicao_tools import predicoes_atingimento_meta

TOOLS = [
    ciclo_visao_geral,
    ciclo_riscos_pendencias,
    predicoes_atingimento_meta,
]
