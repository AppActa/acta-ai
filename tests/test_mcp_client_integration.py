import os
import unittest

from clients.mcp_acta_client import call_acta_tool, mcp_request_context


def _enabled(name: str) -> bool:
    return os.getenv(name, "false").lower() in {"1", "true", "yes", "y", "on"}


class MCPClientIntegrationTest(unittest.TestCase):
    @unittest.skipUnless(
        _enabled("ACTA_RUN_MCP_INTEGRATION"),
        "Defina ACTA_RUN_MCP_INTEGRATION=1 com o MCP local ativo.",
    )
    def test_acta_ai_reads_tools_from_mcp(self) -> None:
        os.environ.setdefault("ACTA_MCP_URL", "http://127.0.0.1:8000/mcp")
        with mcp_request_context(usuario_id=1, empresa_id=1):
            result = call_acta_tool("ciclo_visao_geral", {"id_ciclo": 1})

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["ciclo"]["id_empresa"], 1)


if __name__ == "__main__":
    unittest.main()
