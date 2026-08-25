from mcp.server.mcpserver import MCPServer
from src.mcp_handler.tools.groups_tools import register_groups_tools
from src.mcp_handler.tools.payment_methods_tools import register_payment_methods_tools
from src.mcp_handler.tools.expenses_tools import register_expenses_tools

# api-keys (create/search/delete) deliberadamente NO se expone como tools —
# dejar que un LLM cree/revoque sus propias credenciales de acceso es un
# riesgo innecesario; esa gestión sigue siendo directa contra la API/Postman.


def register_tools(mcp: MCPServer):
    register_groups_tools(mcp)
    register_payment_methods_tools(mcp)
    register_expenses_tools(mcp)
