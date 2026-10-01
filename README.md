# Rocha Comércio de Café · App v2.2

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


## Atualização v2.1
- Entrada e saída agora podem ser editadas.
- Ao editar, estoque e saldo devedor são recalculados automaticamente.
- Mantém baixas já registradas e bloqueia alterações que deixariam estoque ou pagamentos inconsistentes.

## Atualização v2.2
- Entrada/compra agora tem condição **À vista** ou **A prazo**.
- O formulário mostra **Total da compra**, **Pago agora** e **Saldo a pagar do fornecedor** antes de salvar.
- Compras a prazo geram automaticamente o saldo em **A pagar**.
- Vendas a prazo geram automaticamente o saldo em **A receber**.
- Cada saída/venda ganhou o botão **Imprimir venda**.
- O comprovante de venda mostra cliente, produto, quantidade, valor unitário, total, condição de pagamento, recebido e saldo pendente.
- Após cadastrar uma nova venda, o sistema oferece imprimir o comprovante na hora.
