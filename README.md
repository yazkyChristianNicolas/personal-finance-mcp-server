# personal-finance-mcp-server

MCP server remoto para [`personal-finance-service`](https://github.com/yazkyChristianNicolas/personal-finance-service):
expone sus operaciones de negocio (grupos, medios de pago, gastos) como
tools MCP, autenticado con Keycloak. Pensado para usarse desde Kiro/Claude
(login interactivo) o desde un agente headless en la nube (login M2M).

## Requisitos

- Docker + Docker Compose
- `personal-finance-service` corriendo (`docker compose up -d` en ese repo) —
  este server se conecta a su Keycloak y su API, no los levanta él mismo.

## Cómo correrlo

```bash
cp .env.example .env
# completar KEYCLOAK_CLIENT_SECRET con el secret de mcp-personal-finance-server
# (ver "Setup de Keycloak" en AGENTS.md si todavía no existen los clients)
docker compose up -d --build
```

- `GET http://localhost:8000/health`
- `POST http://localhost:8000/mcp` — requiere `Authorization: Bearer <jwt>`

## Configuración del MCP en Kiro

```json
{
  "mcpServers": {
    "personal-finance-remote": {
      "url": "http://localhost:8000/mcp",
      "oauth": {
        "clientId": "mcp-personal-finance-client",
        "scopes": []
      }
    }
  }
}
```

Al primer uso, Kiro abre el browser para el login contra Keycloak — usa el
mismo usuario/contraseña que ya usás en `personal-finance-service`.

## Tools disponibles

| Tool | Qué hace |
|---|---|
| `search_groups` | Lista los grupos del usuario |
| `create_group` | Crea un grupo |
| `search_group_members` | Lista los miembros de un grupo |
| `search_payment_methods` | Lista los medios de pago del usuario |
| `create_payment_method` | Crea un medio de pago |
| `patch_payment_method` | Modifica un medio de pago |
| `delete_payment_method` | Elimina un medio de pago |
| `search_expenses` | Lista gastos, con filtros |
| `create_expense` | Registra un gasto (opcionalmente en cuotas y/o dividido) |
| `close_expense_cycle` | Genera la cuota siguiente de los gastos en cuotas de una tarjeta |
| `get_expense` | Detalle completo de un gasto |
| `patch_expense` | Modifica un gasto |
| `delete_expense` | Elimina un gasto |

La gestión de API Keys de `personal-finance-service` (crear/listar/borrar)
deliberadamente **no** está expuesta como tools — ver `AGENTS.md`.

## Agente headless (M2M)

Para un agente sin usuario humano detrás (no puede hacer el login
interactivo), usá Client Credentials Grant en vez del flujo de Kiro:

```bash
curl -X POST http://localhost:8080/realms/personal-finance/protocol/openid-connect/token \
  -d "grant_type=client_credentials&client_id=mcp-personal-finance-agent&client_secret=$AGENT_CLIENT_SECRET" \
  | jq -r .access_token
```

Usá ese `access_token` como Bearer contra `POST /mcp`. El agente además
necesita `UPSTREAM_API_KEY` configurada en su entorno — una Personal Finance
API Key generada de antemano por un usuario real (`POST /api-keys` en
`personal-finance-service`), ya que su token no representa a ningún usuario
real de esa API.

## Más detalle

Ver `AGENTS.md` — decisiones de diseño, gaps conocidos, y por qué el
passthrough de auth funciona (y cuándo dejaría de funcionar).
