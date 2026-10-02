# Material histórico e limites

Os scripts históricos continuam nos caminhos originais na raiz. Eles resolvem
`templates/`, `studyinbr/`, `PT-BR/`, `img/` e relatórios em relação à pasta corrente;
movê-los agora sem adaptadores poderia quebrar operações de manutenção. Não fazem
parte do pacote `studybr` nem da CLI instalada.

Os três módulos de teste anteriores foram movidos, sem mudar expectativas, para
`legacy/tests/`. O Git identifica essas movimentações. Execução explícita, offline:

```sh
python scripts/run_offline_tests.py legacy/tests -o pythonpath=". src" -p no:cacheprovider
```

As cinco falhas históricas de montagem de URL continuam pendentes de confirmação
do endpoint real. Não se presume que `++api++` seja obrigatório.

Não executar os scripts da raiz nesta fase: eles possuem escritas, login,
transições e, no migrador Trensurb, remoção de locks e TLS desabilitado. A credencial
literal de `config.py` foi retirada da árvore ativa; esse módulo agora lê
`PLONE_TOKEN`, sem fallback. O restante do legado não foi refatorado.

As quatro capturas em `html/` foram preservadas sem alteração, pois são evidência
histórica. Contêm material sensível e têm exceções de fingerprint no secret guard.
Isso não torna essas credenciais seguras: revogação/rotação permanece necessária.
Nunca copiar as capturas para novas fixtures ou logs. Histórico Git não foi
reescrito. Novas capturas autenticadas e novos secrets são proibidos.
