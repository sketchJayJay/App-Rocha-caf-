# Rocha Comércio de Café

Sistema web responsivo para controle de:
- Entrada e saída de estoque
- Cadastro de clientes
- Estoque com custo médio e estoque mínimo
- Saldo devedor a receber e a pagar
- Baixa parcial ou total de saldos
- Dashboard com visão geral
- Instalação como PWA no celular

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
```

Abra: http://localhost:5000

## Coolify

Crie um novo recurso a partir do repositório e use o Dockerfile. Porta interna: `5000`.

### Persistência importante

O banco é SQLite e fica no arquivo `rocha_cafe.db`. Em produção, monte um volume persistente em `/app/rocha_cafe.db` (ou em `/app` inteiro) para não perder dados em redeploy.

## Regra dos saldos

- Entrada/compra com valor ainda não pago cria automaticamente um saldo **a pagar**.
- Saída/venda com valor ainda não recebido cria automaticamente um saldo **a receber**.
- Também é possível criar saldos manualmente.
