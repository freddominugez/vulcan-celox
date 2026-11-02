TAREFA: drive-upload-retry repetir upload ao Drive quando a rede cair
C1 [verde]    build passa com o novo cliente      sensor: build
C2 [amarela]  repetição com espera crescente      sensor: typecheck + lint + teste existente
C3 [vermelha] limite de taxa por usuário          sensor: rate-limit.test.ts + revisão separada + rollback
FORA: trocar a biblioteca do Drive
ESCRITA: lib/drive/, tests/drive/
ORÇAMENTO: 3 tentativas por item
APROVAÇÃO: pendente
