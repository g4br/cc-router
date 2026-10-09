# 150 exemplos de tarefas de programação: Luna, Sol e Astra

**Matriz de roteamento:** 3 modelos × 5 níveis de raciocínio × 10 tarefas por combinação.

Este catálogo foi pensado para classificação de subtarefas em um roteador como o **cc-router/Laya**. Os exemplos descrevem **o trabalho que seria delegado** e **o critério concreto de conclusão**, em vez de associar os modelos apenas ao tamanho do código.

## Como interpretar

- **Luna:** preferência por ações locais, mecânicas, bem especificadas e de verificação barata. Mesmo com mais raciocínio, o escopo deve permanecer controlado.
- **Sol:** implementação e depuração de complexidade intermediária, envolvendo algumas dependências, decisões de desenho e integração entre componentes.
- **Astra:** problemas de maior ambiguidade, riscos de regressão, invariantes difíceis ou consequências relevantes de uma decisão errada.
- **`low` → `medium` → `high` → `extra high` → `max`:** orçamento de raciocínio progressivamente maior; **não** são garantias de capacidade, qualidade ou tempo de execução.

> **Compatibilidade:** as 15 combinações aparecem porque foram solicitadas como matriz conceitual. No mapeamento anteriormente considerado para o cc-router, as combinações observadas eram **Luna/low**, **Sol/low, medium, high** e **Astra/medium, high, extra high, max**. As demais seções são **hipotéticas** e só devem ser habilitadas se o provedor realmente oferecer o par modelo/esforço. A classificação deve ser calibrada por custo, latência, taxa de sucesso e testes, não por uma escada rígida de nomes.

## Aplicação no cc-router

Os campos `suited_for` de [config/ladder.json](../config/ladder.json) implementam
uma síntese dos casos observados: escopo, exemplos com verificação, critério de
conclusão e fronteira com os demais perfis. O catálogo ativo continua com oito
pares. `extra high` corresponde ao identificador configurado `xhigh`. A presença
na configuração não comprova disponibilidade na sessão: o host precisa confirmar
o modelo e o esforço efetivos.

| Par configurado | Trabalho adequado | Evidência de conclusão | Fronteira de uso |
|---|---|---|---|
| Luna/low | Edição local, mecânica e especificada | Diff limitado e sintaxe ou saída conhecida conferida | Ambiguidade e criticidade excluem este candidato; poucas linhas não bastam para escolhê-lo |
| Sol/low | Um componente rotineiro, com decisões pequenas de API | Casos normais, inválidos e vazios, sem quebra de contrato | Integrar módulos passa ao perfil medium; recuperação concorrente passa ao high |
| Sol/medium | Funcionalidade completa entre módulos com contratos conhecidos | Integração, expiração, idempotência ou reinício verificáveis | Falhas entre componentes e estado compartilhado exigem avaliar high |
| Sol/high | Integração concorrente ou depuração não local dentro de um desenho definido | Reprodução da falha, recuperação testada e medidas antes/depois quando aplicável | Invariantes de alto impacto ou arquitetura ainda indefinida exigem avaliar Astra |
| Astra/medium | Revisão arquitetural ou diagnóstico multicausal com objetivo explícito | Alternativas confrontadas com restrições e hipóteses testáveis | Implementação rotineira cabe em Sol; invariantes críticos pedem high |
| Astra/high | Correção ou revisão de isolamento, entrega, integridade e cancelamento | Invariantes demonstradas com regressão, testes adversariais ou equivalência numérica | Especificação incompleta e restrições conflitantes podem justificar xhigh |
| Astra/xhigh | Decisão arquitetural complexa sob falhas e trade-offs | Premissas explícitas, alternativas comparadas e cenários de recuperação validados | Exige aprovação na configuração; quantidade de arquivos não demonstra necessidade |
| Astra/max | Investigação excepcional com alto impacto e benefício esperado justificável | Reprodução ou formalização, equivalência e critérios de recuperação | Exige aprovação e é `escalation_only`: uma tentativa anterior ou `user_floor` correspondente permite sua elegibilidade, mas não garante seleção |

### Como os perfis entram na decisão

- **`backend: heuristic` (padrão):** usa `operation`, `files`, `ambiguous` e
  `critical`, além de restrições e histórico. Não interpreta semanticamente os
  exemplos nem a descrição. Perfis refinados não alteram essa fórmula.
- **`backend: laya`, `laya_mode: per_candidate`:** envia cada `suited_for` na
  pergunta de adequação ao candidato, nas duas ordens de resposta. Os exemplos
  ajudam a avaliar a tarefa, mas os escores continuam não calibrados; elegibilidade,
  política e aprovações ainda se aplicam.
- **`laya_mode: difficulty`:** classifica a descrição e a operação em cinco níveis,
  combinados com a heurística. Não consome os perfis individuais nem representa
  diretamente todas as oito combinações. Consulte [Laya](laya.md).

No fallback sem observações comparáveis, com até três arquivos e ambas as flags
falsas, `mechanical_edit` parte de Luna/low, `tweak` de Sol/low,
`implementation` de Sol/medium, `debugging` de Sol/high, `review` ou
`architecture` de Astra/medium e `security` ou `investigation` de Astra/high.
Cada sinal (`files > 3`, `ambiguous`, `critical`) acrescenta um degrau antes das
restrições. Essa aproximação pode divergir da classificação conceitual: uma
implementação de componente ainda parte de Sol/medium quando declarada como
`implementation`. Informe a operação real; não manipule flags para obter um modelo.

### Casos de fronteira

- **SQL:** um JOIN com cardinalidade conhecida cabe no perfil Sol/low; decidir
  armazenamento por padrões reais de consulta cabe em Astra/medium. A linguagem
  usada não determina o modelo.
- **Cache:** TTL com expiração testável cabe em Sol/medium; recarga concorrente
  com falha reproduzível cabe em Sol/high; consistência entre versões com impacto
  crítico cabe em Astra/high.
- **Segurança:** renomear uma variável local num módulo de autenticação pode ser
  mecânico; avaliar revogação de sessões exige revisão; provar isolamento entre
  tenants exige examinar invariantes e regressões em várias camadas.
- **Migração:** adicionar uma coluna com contrato e rollback conhecidos pode
  caber em Sol/medium; manter duas versões compatíveis sem parada exige avaliar
  Astra/high; dual-write crítico sob carga com divergências ainda não resolvidas
  pode justificar escalonamento adicional.

As combinações hipotéticas abaixo são material de avaliação, não destinos de
fallback. Não converta automaticamente Luna/high em Luna/low ou Sol/max em
Astra/max: reavalie o trabalho entre os candidatos elegíveis e confirme o suporte
antes de adicionar um par. Esforço maior pode ajudar na deliberação, mas não
substitui capacidade, contexto ou ferramentas ausentes.

Falhas de verificação ou raciocínio seguem o escalonamento implementado no
[protocolo](protocol.md), após diagnóstico e verificação do diff. Ele avança um
nível de dificuldade (ou um degrau acima do topo), podendo trocar de modelo.
Não há política automática de sempre esgotar os esforços do mesmo modelo.
Falhas de ambiente, permissão ou quota não são evidência para aumentar esforço.

## 1. Luna

### Luna · low — edições pontuais e determinísticas
**Perfil:** entrada e saída explícitas; poucas linhas; pouca necessidade de investigação. **Status:** combinação observada.

1. **Corrigir indentação de um dicionário Python:** alinhar chaves e vírgulas sem mudar valores; conferir a sintaxe com `ast.parse`.
2. **Renomear variável local:** substituir `temp` por `temperatura_c` em uma função, preservando a assinatura pública e as demais referências.
3. **Adicionar uma docstring:** documentar parâmetros e retorno de uma função cuja implementação já determina o contrato.
4. **Ajustar formatação `f-string`:** imprimir horas com dois dígitos ou números com uma casa decimal; testar dois exemplos conhecidos.
5. **Alterar uma cor CSS:** trocar um hexadecimal em uma classe específica sem modificar os demais estilos.
6. **Converter uma lista em conjunto:** remover duplicatas de nomes de arquivos preservando, quando exigido, a ordem de primeira ocorrência.
7. **Escrever um `grep` simples:** filtrar linhas contendo um erro literal em arquivo de log, sem interpretar o padrão como expressão regular.
8. **Corrigir caminho com `pathlib`:** substituir concatenação manual de separadores por `Path(base) / nome` em um único ponto.
9. **Adicionar argumento padrão:** tornar opcional uma flag booleana em função sem afetar chamadas existentes.
10. **Criar teste de igualdade:** acrescentar um teste unitário para uma conversão aritmética já definida e sem dependências externas.

### Luna · medium — pequenas funções com validação de entrada
**Perfil:** regras claras, alguns casos extremos e uma ou duas funções. **Status:** combinação hipotética.

1. **Validar colunas de CSV:** informar quais cabeçalhos obrigatórios faltam antes de processar o arquivo; testar CSV completo e incompleto.
2. **Filtrar DataFrame por período:** selecionar registros entre duas datas inclusivas, tratando strings inválidas como erro explícito.
3. **Adicionar uma CLI com `argparse`:** aceitar caminho de entrada e saída para um script existente; manter o comportamento padrão.
4. **Criar conversor de unidade:** passar Kelvin para Celsius e preservar `NaN` em uma série NumPy; testar valores-limite.
5. **Tratar retorno HTTP vazio:** distinguir resposta sem conteúdo, JSON válido e falha de decodificação em um cliente simples.
6. **Gerar nomes de arquivos em UTC:** padronizar `YYYYMMDD_HHMM` em uma função com testes para mudança de dia.
7. **Carregar configuração YAML:** aplicar valores padrão e rejeitar chaves obrigatórias ausentes sem gerar exceções obscuras.
8. **Criar formulário JS básico:** validar campos obrigatórios antes do `fetch` e exibir erro de preenchimento ao usuário.
9. **Agrupar contagens por categoria:** calcular ocorrências de códigos meteorológicos com `groupby` sem contar campos nulos indevidamente.
10. **Implementar `/health`:** adicionar rota FastAPI que retorna estado e versão do serviço, coberta por teste de resposta HTTP.

### Luna · high — lógica local com múltiplos casos extremos
**Perfil:** algoritmo curto, porém com combinações de entrada que exigem testes cuidadosos. **Status:** combinação hipotética.

1. **Converter CSV em JSON Lines:** ignorar linhas vazias, reportar linhas inválidas e manter a ordem original dos registros.
2. **Normalizar acumulados de precipitação:** converter metros para milímetros em `xarray` usando metadados e evitando multiplicar duas vezes.
3. **Criar `debounce` em JavaScript:** reduzir chamadas da busca durante digitação e cancelar o temporizador ao desmontar o componente.
4. **Extrair campos de logs variáveis:** interpretar carimbo de data, nível e mensagem, inclusive quando a mensagem contém colchetes.
5. **Baixar um arquivo com retomada simples:** usar `Range` somente quando o servidor permitir; verificar o tamanho final.
6. **Inspecionar um NetCDF:** checar variáveis obrigatórias, dimensão temporal não vazia e atributos de unidade antes do processamento.
7. **Gravar JSON atomicamente:** escrever em arquivo temporário e substituir o destino somente após serialização bem-sucedida.
8. **Calcular totais mensais:** agrupar série diária com calendário correto, preservar meses sem registros e evitar duplicação de datas.
9. **Diagnosticar travessia de diretórios:** gerar script que mostre permissões em cada pasta ancestral antes de recomendar uma ACL.
10. **Criar tooltip no Leaflet:** mostrar valor, unidade e timestamp de um ponto sem recriar listeners a cada atualização.

### Luna · extra high — depuração difícil, mas contida
**Perfil:** raciocínio mais profundo em um módulo isolado; escalar caso a causa não seja local. **Status:** combinação hipotética.

1. **Rastrear erro de codificação:** descobrir por que um CSV mistura UTF-8 e Latin-1 e propor tratamento determinístico com teste de amostra.
2. **Corrigir bug de virada do mês:** reproduzir agregação que desloca dados em UTC para o mês errado e fixar o fuso em um ponto.
3. **Detectar conversões silenciosas de tipo:** localizar onde identificadores com zeros à esquerda viram inteiros e preservar o contrato.
4. **Reescrever regex ambígua:** eliminar capturas incorretas em nomes de produtos GRIB com prefixos parecidos e fixar casos negativos.
5. **Investigar teste intermitente simples:** identificar dependência de relógio real e torná-la controlada por injeção de tempo.
6. **Comparar duas configurações aninhadas:** produzir um diff estável de chaves e valores, sem confundir ausência com `null`.
7. **Evitar erro de precisão decimal:** substituir comparação exata de `float` por tolerância justificada e registrar testes de fronteira.
8. **Corrigir seleção por longitude:** identificar mistura entre grades `0–360` e `−180–180` ao consultar um ponto com `xarray`.
9. **Resolver conflito de nomes em módulos:** diagnosticar importação do arquivo local `json.py` em vez da biblioteca padrão.
10. **Remover vazamento de estado entre testes:** localizar fixture mutável compartilhada e garantir independência com execução em ordem aleatória.

### Luna · max — limite superior de tarefas locais
**Perfil:** investigações pequenas que exigem provar vários casos; usar principalmente para experimento de custo/qualidade. **Status:** combinação hipotética.

1. **Provar correção de uma janela temporal:** testar limites aberto/fechado, horário de verão e timestamps repetidos em uma única função.
2. **Reproduzir perda de linhas no parser:** construir casos mínimos para quebras de linha dentro de aspas e corrigir apenas o parser.
3. **Detectar dupla conversão de unidades:** rastrear a cadeia local de `kg m⁻²` para `mm` e impedir uma segunda conversão.
4. **Derivar casos extremos de arredondamento:** criar testes parametrizados para limiares `>=` e `>` de um score agronômico.
5. **Encontrar a origem de duplicatas:** seguir uma chave composta entre dois `merge` de pandas e corrigir cardinalidade inesperada.
6. **Estabilizar ordenação de eventos:** resolver empate entre timestamps iguais usando critério secundário documentado.
7. **Verificar função de interpolação:** testar monotonicidade, limites e preservação de pontos conhecidos em um algoritmo curto.
8. **Consertar cache em memória isolado:** identificar quando chave mutável causa colisões e definir representação imutável.
9. **Auditar serialização de `NaN`:** impedir JSON não conforme em uma resposta pontual e conferir comportamento de consumidores.
10. **Diagnosticar deadlock em duas travas locais:** criar reprodução mínima e impor ordem única de aquisição, sem redesenhar o serviço.

## 2. Sol

### Sol · low — implementação rotineira de componentes
**Perfil:** tarefa definida com algumas decisões de API ou organização. **Status:** combinação observada.

1. **Criar endpoint de consulta:** receber `lat`, `lon` e data em FastAPI, validar intervalos e devolver um objeto JSON simples.
2. **Implementar componente React:** montar seletor de modelo com estado controlado, mensagens de erro e callback de alteração.
3. **Escrever consulta SQL com `JOIN`:** reunir estações e observações pela chave correta, tratando estações sem leituras.
4. **Adicionar paginação:** incluir `limit` e `offset` em rota existente, com limites máximos e ordenação estável.
5. **Plotar série temporal:** gerar gráfico Matplotlib de temperatura com rótulos, unidade e tratamento de valores ausentes.
6. **Criar teste de API:** usar `pytest` e `TestClient` para status 200, dados inválidos e recurso inexistente.
7. **Adicionar retry de HTTP:** usar espera exponencial limitada apenas em erros transitórios e preservar erros definitivos.
8. **Escrever Dockerfile Python:** instalar dependências fixadas, rodar como usuário sem privilégios e definir comando de execução.
9. **Criar componente de legenda:** representar classes de precipitação com cores e limiares oriundos de configuração.
10. **Implementar conversão geográfica:** preparar GeoJSON de pontos a partir de latitude/longitude e validar geometrias.

### Sol · medium — funcionalidades de ponta a ponta
**Perfil:** integração entre módulos e testes de contrato previsíveis. **Status:** combinação observada.

1. **Criar ingestão de estações:** consumir API paginada, validar leituras, normalizar UTC e gravar no banco com chave idempotente.
2. **Implementar cache TTL em FastAPI:** guardar respostas por parâmetros normalizados e definir política de expiração testável.
3. **Construir painel meteorológico:** integrar endpoint, gráfico React e estados de carregamento, vazio e erro.
4. **Automatizar CDO:** montar pipeline para concatenar NetCDF e calcular somas mensais, verificando calendário e unidades.
5. **Subir stack com Docker Compose:** configurar API, banco e frontend com volumes, rede interna e health checks.
6. **Refatorar rotas Flask:** separar validação, serviço e resposta sem alterar URLs e formatos retornados.
7. **Criar migração de banco:** incluir coluna com valor padrão, popular dados antigos e prever rollback quando possível.
8. **Escrever testes E2E:** cobrir login e consulta de dados em navegador, com fixtures reproduzíveis.
9. **Gerar tiles GeoJSON:** dividir feições por área geográfica, otimizar payload e manter identificadores estáveis.
10. **Implementar job agendado:** processar arquivos novos, registrar sucesso/falha e evitar reprocessamento após reinício.

### Sol · high — integração com falhas e concorrência
**Perfil:** vários componentes, estados concorrentes e necessidade de reproduzir falhas. **Status:** combinação observada.

1. **Resolver cache desatualizado:** coordenar recarga de modelos em memória enquanto requisições continuam sendo atendidas.
2. **Criar downloader paralelo:** limitar conexões, aplicar backoff e garantir integridade de arquivos parcialmente baixados.
3. **Migrar API síncrona para assíncrona:** retirar chamadas bloqueantes do event loop sem mudar contratos existentes.
4. **Investigar vazamento de memória:** localizar retenção em listas de tarefas e caches de `xarray` com perfis antes/depois.
5. **Construir fila de processamento:** executar jobs de GRIB com deduplicação, retries e recuperação de jobs interrompidos.
6. **Projetar testes de pipeline:** validar dados de entrada, somas por período e saída espacial usando conjuntos sintéticos.
7. **Refatorar frontend com estado global:** separar filtros, dados e seleção geográfica sem renderizações desnecessárias.
8. **Otimizar consulta geoespacial:** comparar índices, filtros bounding box e planos SQL com medidas reproduzíveis.
9. **Integrar websocket de telemetria:** reconectar clientes, descartar eventos obsoletos e limitar uso de memória.
10. **Corrigir bug entre fusos horários:** alinhar API, banco e UI diante de timestamps ingênuos e offset explícito.

### Sol · extra high — desenho técnico exigente
**Perfil:** várias estratégias plausíveis, restrições conflitantes e necessidade de justificar escolhas. **Status:** combinação hipotética.

1. **Planejar scheduler em DAG:** executar etapas dependentes e paralelas com limite de recursos e propagação de falhas.
2. **Projetar ingestão multiprovedor:** unificar GFS, ECMWF e ICON em contrato interno sem perder metadados específicos.
3. **Eliminar condição de corrida:** impedir que duas instâncias publiquem o mesmo produto durante atualizações simultâneas.
4. **Reestruturar aplicativo monolítico:** extrair camadas de coleta, cálculo e visualização com migração gradual e testes.
5. **Desenhar cache de grades espaciais:** escolher estratégia de chunking, compressão e invalidação sob restrição de RAM.
6. **Criar gateway BLE→HTTP:** ler PIDs OBD2 no ESP32 e publicar telemetria com reconexão e dados inválidos tratados.
7. **Comparar algoritmos de interpolação:** definir benchmark de custo, erro e conservação dos dados em grades distintas.
8. **Rever política de retries:** diferenciar falha temporária, saída parcial e erro permanente ao longo de um workflow.
9. **Implementar atualização sem parada:** trocar datasets usados por processos de API sem servir versões misturadas.
10. **Definir protocolo de plugins:** permitir novos processadores mantendo versionamento, validação e isolamento de erros.

### Sol · max — investigações sistêmicas em escopo delimitado
**Perfil:** engenharia complexa com restrições explícitas e pontos de validação; comparar custo com Astra. **Status:** combinação hipotética.

1. **Diagnosticar gargalo de ponta a ponta:** separar custo de disco, CPU, descompressão GRIB e serialização com perfil e hipótese testada.
2. **Construir executor paralelo resiliente:** garantir dependências, cancelamento, timeout e persistência do estado de cada tarefa.
3. **Desenhar migração de formato espacial:** trocar arquivos NetCDF por Zarr em uma área da plataforma preservando os resultados.
4. **Criar camada de compatibilidade:** suportar duas versões da API durante atualização gradual de clientes sem duplicar a lógica.
5. **Investigar inconsistência entre réplicas:** reproduzir leitura de dados antigos e corrigir política de publicação atômica.
6. **Otimizar cálculo distribuído:** comparar `dask` por chunks e processamento local em um workload com orçamento de memória.
7. **Implementar validação científica cruzada:** comparar precipitação de duas rotinas independentes e explicar divergências por calendário e unidade.
8. **Projetar fallback multi-modelo:** reexecutar subtarefa em modelo mais forte quando teste, confiança ou limite operacional falhar.
9. **Revisar integração CAN/OBD2:** separar transporte, parsing de frames e exibição para conter timeouts e leituras corrompidas.
10. **Conduzir refatoração guiada por testes:** isolar módulo legado com muitas dependências e manter equivalência de comportamento mensurável.

## 3. Astra

### Astra · low — avaliação especializada com objetivo explícito
**Perfil:** usar experiência de um modelo forte em resposta curta, com pouca deliberação. **Status:** combinação hipotética.

1. **Revisar contrato de uma API pública:** identificar incompatibilidades óbvias de payload e sugerir correção mínima, sem redesenho.
2. **Avaliar índice SQL proposto:** julgar se as colunas acompanham filtro e ordenação de uma consulta conhecida.
3. **Identificar risco em `pickle`:** apontar desserialização insegura de dados externos e substituição por formato apropriado.
4. **Revisar trecho concorrente curto:** verificar uso incorreto de `asyncio.create_task` sem controle de ciclo de vida.
5. **Validar estratégia de versionamento:** conferir se mudança de resposta JSON exige compatibilidade retroativa.
6. **Conferir fórmula física implementada:** apontar mistura evidente de Kelvin e Celsius em cálculo já especificado.
7. **Revisar política de segredos:** detectar token de API em repositório ou log e propor migração para variável de ambiente.
8. **Escolher estrutura de dados:** comparar heap, fila e lista para um requisito de prioridade bem definido.
9. **Criticar plano de migração simples:** detectar falta de backup, checagem ou rollback em script de alteração de esquema.
10. **Avaliar fronteira de componentes:** indicar acoplamento forte entre visualização React e parser de dados em caso concreto.

### Astra · medium — revisão arquitetural e diagnóstico multicausal
**Perfil:** decisões que cruzam camadas e admitem mais de uma solução viável. **Status:** combinação observada.

1. **Investigar travamentos intermitentes:** correlacionar métricas, logs e filas para priorizar causas testáveis antes de alterar código.
2. **Revisar desenho de autenticação:** confrontar sessões, tokens, refresh e revogação com os fluxos efetivos do aplicativo.
3. **Planejar separação de serviços:** decidir o que manter no monólito e o que extrair considerando custo operacional e consistência.
4. **Auditar parsing de GRIB2:** verificar interpretação de ciclos, passos acumulados e mensagens duplicadas em produtos distintos.
5. **Comparar bancos para séries temporais:** ponderar DuckDB, PostgreSQL/Timescale e arquivos colunares segundo consultas reais.
6. **Definir tolerâncias científicas:** escolher métricas para validar equivalência numérica entre implementações com float diferente.
7. **Revisar pipeline de CI:** encontrar lacunas em testes, cache de build, permissões e publicação de artefatos.
8. **Projetar observabilidade:** correlacionar requisição, modelo meteorológico e versão do dataset em logs e métricas.
9. **Avaliar arquitetura do roteador Laya:** separar classificador, política, planejador, executor e validação sem ciclos de dependência.
10. **Analisar incidentes de banco:** distinguir corrida de escrita, isolamento de transação e perda de idempotência com roteiro de reprodução.

### Astra · high — correção de sistemas críticos e invariantes
**Perfil:** grandes efeitos de regressão, múltiplas hipóteses e exigência forte de evidências. **Status:** combinação observada.

1. **Eliminar perda de eventos:** revisar fila distribuída e estabelecer semântica de entrega, deduplicação e recuperação testadas.
2. **Auditar autorização multiusuário:** verificar isolamento entre contas em rotas, queries, caches e armazenamento de objetos.
3. **Corrigir erro de concorrência raro:** reconstruir sequência temporal a partir de traces e reproduzir o estado incorreto.
4. **Validar previsão de acumulados:** provar que conversão de acumulado desde o ciclo para chuva horária não cria valores falsos.
5. **Projetar atualização de schema sem parada:** coordenar duas versões de aplicação com escrita e leitura compatíveis.
6. **Revisar parser de protocolo binário:** tratar tamanho, checksum, truncamento e sequências inesperadas com testes fuzz.
7. **Garantir consistência de cache:** definir chaves e invalidação quando produtor e consumidores leem versões diferentes do mesmo dado.
8. **Construir modelo de ameaças:** identificar superfícies de ataque do app e priorizar controles verificáveis de maior risco.
9. **Otimizar sem mudar resultados:** propor mudança de algoritmo após benchmark, testes de equivalência e limites numéricos.
10. **Validar scheduler de agentes:** impedir execução duplicada e resultados de subtarefas canceladas em fluxos paralelos.

### Astra · extra high — decisões complexas com trade-offs profundos
**Perfil:** arquitetura sensível, especificações incompletas e necessidade de comparar alternativas sob falhas. **Status:** combinação observada.

1. **Redesenhar ingestão em escala:** definir contratos, particionamento e recuperação para múltiplos modelos NWP com chegada irregular.
2. **Projetar sistema transacional de tarefas:** coordenar agendamento, reexecução, efeitos externos e consistência após crash.
3. **Auditar mecanismo de atualização remota:** revisar assinatura, rollback e integridade de firmware ESP32 sob interrupções de energia.
4. **Conduzir análise de causa-raiz:** reconciliar traces incompletos e mudanças recentes para explicar falha reproduzível em produção.
5. **Definir isolamento multi-tenant:** considerar autenticação, autorização, cache, filas e telemetria em uma única arquitetura.
6. **Criar plano de migração multi-etapas:** mover dados históricos volumosos sem interromper consultas e com critérios de reversão.
7. **Projetar sistema de avaliação do roteador:** medir qualidade, custo, latência e escalonamento sem viés de seleção nos testes.
8. **Rever integridade de dados científicos:** rastrear proveniência, ciclos, calendários e transformações de cada valor disponibilizado.
9. **Arquitetar execução sob recursos limitados:** combinar processos Python, Dask e armazenamento local sem exaustão de RAM ou disco.
10. **Comparar estratégias de sincronização:** avaliar locks distribuídos, filas e versões imutáveis diante de particionamento de rede.

### Astra · max — problemas excepcionalmente difíceis e de alto impacto
**Perfil:** investigação extensa e multidisciplinar; só justificar quando o ganho esperado superar claramente custo e latência. **Status:** combinação observada.

1. **Planejar migração crítica sem downtime:** coordenar esquemas, backfill, dual-write, verificação de divergências e rollback sob carga real.
2. **Investigar corrupção rara de dados:** combinar rastros de memória, concorrência, I/O e formato binário até obter reprodução determinística.
3. **Formalizar invariantes do scheduler:** especificar estados, transições e impossibilidade de publicar resultado de tarefa cancelada.
4. **Desenhar arquitetura tolerante a falhas regionais:** definir RPO/RTO, replicação, consistência e simulações de indisponibilidade.
5. **Auditar cadeia de suprimentos de software:** mapear dependências, builds reproduzíveis, credenciais e política de assinatura de artefatos.
6. **Criar estratégia de testes adversariais:** gerar propriedades, fuzzing e cenários de falha para uma biblioteca central de protocolos.
7. **Reconciliar resultados científicos conflitantes:** verificar métodos independentes de agregação espacial/temporal e demonstrar origem dos desvios.
8. **Projetar roteador autoavaliável:** selecionar modelo/esforço por custo esperado, medir falhas e evitar degradar qualidade em produção.
9. **Redesenhar plataforma com compatibilidade integral:** modularizar sistema legado preservando contratos externos, dados históricos e comportamento medido.
10. **Conduzir revisão técnica de alto risco:** avaliar segurança, concorrência, integridade, observabilidade e plano de recuperação antes de uma mudança irreversível.

## Regras práticas para o roteador

1. **Primeiro classifique o trabalho, depois o esforço.** Modelo e nível de raciocínio são duas decisões: custo/capacidade não dependem apenas da posição em uma lista.
2. **Prefira a menor combinação validada** que complete a tarefa dentro do orçamento de erro. Para trabalho mecânico, verificação automática pesa mais que raciocínio prolongado.
3. **Aumente o esforço antes de trocar de modelo** apenas quando o gargalo for deliberação. Se faltar capacidade de contexto, ferramentas ou conhecimento, trocar de modelo pode ser melhor.
4. **Escalone por sinal observável:** testes quebrados, divergência de contrato, baixa cobertura, incerteza não resolvida, risco elevado ou falha repetida.
5. **Decomponha pedidos grandes:** roteie subtarefas separadamente; por exemplo, Luna corrige nomes, Sol implementa a API e Astra revisa uma migração crítica.
6. **Meça o resultado:** registre `(modelo, esforço, tokens, latência, sucesso nos testes, retrabalho)` para calibrar as regras do cc-router.
7. **Rejeite combinações indisponíveis:** mapeie para pares realmente suportados pelo provedor antes de chamar o executor.

### Exemplo de decisão

**Pedido:** “Criar uma API de previsão do tempo com cache e colocar em produção.”

- **Luna/low:** ajustar docstrings, arquivos de configuração ou formatação em subtarefas bem especificadas.
- **Sol/medium:** implementar endpoints, cache TTL, serialização e testes de integração.
- **Sol/high:** testar concorrência na atualização do cache e tratar falhas de rede.
- **Astra/high:** revisar consistência entre versões de dados, autorização e estratégia de publicação se houver impacto em produção.

**Observação:** estes são *exemplos de roteamento*, não um benchmark que comprove superioridade de uma combinação. Uma decisão de produção precisa ser validada com tarefas e testes representativos do repositório real.
