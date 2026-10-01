# Rocha Comércio de Café · App v2

Sistema web/PWA com visual premium e experiência pensada para celular.

## O que controla

- Entrada / compra e saída / venda
- Cadastro de clientes e fornecedores
- Estoque com custo médio, preço de venda e estoque mínimo
- Saldo devedor a receber e a pagar
- Baixas parciais ou totais
- Dashboard com resumo do negócio e fluxo do mês
- Instalação no Android, iPhone e computador como aplicativo

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
```

Abra `http://localhost:5000`.

## Coolify

Use o Dockerfile do projeto.

**Porta interna:** `5000`

### Persistência do banco

O banco SQLite fica em `/app/rocha_cafe.db`. Configure volume persistente nesse caminho, ou monte `/app` inteiro, para os dados não sumirem em um redeploy.

## Instalar no celular

### Android / Chrome
O sistema oferece o botão de instalação quando o navegador permitir.

### iPhone / Safari
Abra no Safari → Compartilhar → **Adicionar à Tela de Início**.

O sistema abre em modo standalone, sem a barra normal do navegador, com ícone próprio e navegação inferior de app.

## Regra automática dos saldos

- Entrada/compra com valor ainda não pago cria saldo **a pagar**.
- Saída/venda com valor ainda não recebido cria saldo **a receber**.
- Também é possível lançar saldos manualmente.
