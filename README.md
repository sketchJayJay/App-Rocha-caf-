# Rocha Comércio de Café · Rocha One Executive v3.0

Sistema web/PWA premium para controle de entrada, saída, clientes, estoque e saldos.

## Destaques da versão 3.0

- Dashboard executivo totalmente redesenhado
- Gráfico dos últimos 6 meses de compras e vendas
- Ticket médio e quantidade de vendas/entradas do mês
- Produto e cliente em destaque no mês
- Relatório mensal pronto para imprimir ou salvar em PDF
- Interface mobile com aparência de aplicativo nativo
- Compras à vista e a prazo com saldo automático do fornecedor
- Vendas à vista e a prazo com saldo automático do cliente
- Impressão de comprovante de venda
- Edição de entradas e saídas com recálculo de estoque e financeiro
- PWA para iPhone, Android e computador

## Coolify

**Porta interna:** `5000`

### Persistência do banco

A partir desta versão, o banco é gravado em:

```text
/data/rocha_cafe.db
```

No Coolify, mantenha um volume persistente com:

```text
Destination Path: /data
```

Exemplo de nome de volume:

```text
rocha-cafe-data
```

O nome do volume pode variar. O importante é o destino `/data`.

### Importante ao migrar de uma versão antiga

Se a versão anterior já possui dados e o banco ainda está em `/app/rocha_cafe.db`, copie esse arquivo para `/data/rocha_cafe.db` antes do primeiro redeploy desta versão. Depois disso, os próximos redeploys usam o volume persistente normalmente.

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
```

Abra `http://localhost:5000`.

## Instalar no iPhone

Safari → Compartilhar → **Adicionar à Tela de Início**.
