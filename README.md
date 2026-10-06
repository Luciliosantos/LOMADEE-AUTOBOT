# 🤖 Lomadee Auto Offers Bot

Bot multi-cliente para Telegram. Cada cliente cadastra a própria **API Key da Lomadee**, configura o próprio grupo e ativa a publicação automática.

## Fluxo

`Cliente → API Key Lomadee → Produtos → seleção → imagem → texto → link afiliado → grupo Telegram`

Cada cliente possui configuração isolada:

- API Key Lomadee própria
- grupo/canal próprio
- limite diário próprio
- estado de automação próprio
- histórico de ofertas publicadas próprio

## API Lomadee

A integração usa a URL base de produção:

`https://api.lomadee.com.br`

Autenticação:

`x-api-key: SUA_API_KEY`

Endpoints configuráveis no `.env`:

- `GET /affiliate/products`
- `GET /affiliate/brands`
- `GET /affiliate/campaigns`
- `GET /affiliate/channels`
- `GET /affiliate/orders`
- `GET /affiliate/shortener/urls`

**Importante:** o projeto não inventa um endpoint de criação de DeepLink. A permissão mostrada na documentação para o shortener é de leitura (`shortener:read`). Se a documentação da sua conta mostrar um endpoint de criação, configure `LOMADEE_SHORTENER_CREATE_URL` com a rota oficial.

## Instalação no VPS Ubuntu

```bash
unzip lomadee-auto-bot.zip
cd lomadee-auto-bot
chmod +x install.sh
./install.sh
```

O instalador pede somente:

1. Token do bot Telegram
2. Seu ID numérico do Telegram

Ele gera automaticamente `MASTER_KEY`, cria o ambiente Python, SQLite e serviço systemd.

## Comandos do cliente

- `/start`
- `/lomadee`
- `/grupo`
- `/ativar`
- `/pausar`
- `/teste`
- `/status`
- `/indicacao`
- `/ajuda`

## Grupo Telegram

O cliente deve adicionar o bot como administrador e executar `/grupo` dentro do grupo. O bot grava o `chat_id` daquele cliente.

## Segurança

- API Keys são criptografadas no SQLite.
- `MASTER_KEY` fica no `.env` e não deve ser enviado ao GitHub.
- `.env`, banco e logs estão no `.gitignore`.
- Nunca coloque token Telegram ou API Key em código-fonte.

## GitHub

Depois de criar/conectar o repositório:

```bash
./scripts/publish-github.sh Lomadee-Auto-Bot
```

Com GitHub CLI autenticado, o script mostra o comando para criar o repositório privado e fazer o primeiro push.

## Atualizar VPS depois do GitHub

```bash
./scripts/update-vps.sh
```

## Próxima etapa de integração

A estrutura já está pronta para usar os endpoints reais. Antes de ativar a geração automática de links, confirme na documentação da Lomadee qual operação cria o link/deeplink; não devemos inventar essa rota.
