# Sorteio de Temas — Design

> Status: aprovado no brainstorm de 2026-11-16 (substitui o rascunho
> `2026-11-15-theme-draw-session-handoff.md`, que ficou só no checkout principal).
> Referência visual de inspiração: [`assets/theme-draw-recap-reference.png`](assets/theme-draw-recap-reference.png)
> (recap do edhplay — só a ideia de estrutura, não copiar marca nem layout à risca).

## Intenção

O pod quer variar as partidas: alguém abre uma página, escolhe 4 jogadores do
pod e o app sorteia um **tema de EDH diferente para cada um** (Voltron,
Aristocrats, Elves…, a lista de temas/tags do EDHREC). Cada jogador vê o que
o tema é (volume de decks, top comandantes, um resumo curto em pt-BR) e o
resultado vira uma **imagem para mandar no grupo do WhatsApp**.

O sorteio fica salvo para que o mesmo tema não volte no pod na mesma semana.

## Objetivos

- Sortear 4 temas distintos para 4 jogadores escolhidos do pod.
- Não repetir, dentro do mesmo pod, um tema já sorteado na semana corrente.
- Mostrar por tema: nome, nº de decks no EDHREC, top 3 comandantes, resumo
  pt-BR de até ~120 caracteres.
- Gerar uma imagem 1080×1350 (layout "A · Lista", abaixo) e compartilhar pelo
  celular.

## Não-objetivos (primeira etapa)

- Cores/identidade de cor do tema — um tema não tem cor própria (no EDHREC é
  só uma distribuição de combinações), então **não aparece em lugar nenhum**.
- Cartas-chave/alta sinergia na tela ou na imagem.
- Filtro/curadoria de temas (corte por popularidade, chave "ativo"): **os 420
  temas entram**, inclusive typal e genéricos (Good Stuff, Midrange…).
- Re-sortear o tema de um jogador só; histórico/listagem de sorteios;
  vincular sorteio a partidas ou placar.
- Atualização automática agendada do catálogo (cron do Render é pago).
- Título e data na imagem.

## Anti-objetivos

- O sorteio **não pode depender do EDHREC estar no ar** nem de o EDHREC aceitar
  chamadas vindas do Render.
- O sorteio **não pode ficar travado esperando a LLM**.
- Nada da marca do edhplay na imagem.

## Abordagens consideradas

1. **Catálogo inteiro pré-carregado por management command (escolhida).**
   Um comando busca a lista de temas e a página de cada tema no EDHREC e salva
   tudo no banco; o sorteio só lê do banco. Escolhida porque isola a parte mais
   frágil (API não oficial do EDHREC) fora do caminho do usuário; ranking de
   comandante por tema muda devagar, atualizar ~1x/mês basta.
2. **Buscar detalhes do tema no EDHREC na hora do sorteio**, com cache de uma
   semana. Dados sempre frescos, mas o sorteio passa a depender do EDHREC e fica
   mais lento na primeira vez. Descartada pelo anti-objetivo acima.
3. **Opção 1 + cron semanal.** Descartada por custo (cron pago no Render) e por
   não ser necessária.

Resumo pt-BR: gerado por LLM (Gemini) **na primeira vez que o tema sai num
sorteio**, salvo no tema e nunca mais regerado automaticamente. Decidido após
verificar que o JSON do EDHREC **não traz texto descritivo** (campo
`description` vazio em todos os temas testados).

Imagem: layout "A · Lista" escolhido entre três (A lista, B grade 2×2, C capa +
1 imagem por jogador).

## Fonte de dados: EDHREC (verificado em 2026-11-16)

API JSON não oficial e sem chave. Endpoints que funcionam:

- `https://json.edhrec.com/pages/tags.json` — catálogo. Em
  `container.json_dict.cardlists[0].cardviews` (header "Tags By Popularity
  Sort") há 420 itens com `name`, `url` (`/tags/<slug>`) e contagem de decks
  (campo `num_decks` ou `count` — confirmar qual na implementação).
- `https://json.edhrec.com/pages/tags/<slug>.json` — detalhe do tema. Em
  `container.json_dict.cardlists`, a lista com `tag == "topcommanders"` traz os
  comandantes em ordem de ranking (`name`, `sanitized`, `num_decks`).
- Os caminhos do rascunho (`/pages/themes.json`, `/pages/typal.json`) dão 403.
- Typal (ex.: `elves`) vive no mesmo namespace `/tags/`.

Regras de uso: User-Agent identificável (como já se faz com o Scryfall),
no máximo ~5 req/s, cliente isolado (`EdhrecThemeClient`) para que mudanças na
API fiquem num lugar só.

## Modelo de dados

### `apps/cards` (dado global, nunca filtrado por pod)

`Theme` — em `apps/cards/models.py` (a app usa um único `models.py`):

| campo | tipo | nota |
|---|---|---|
| `slug` | CharField, unique | slug do EDHREC (`plus-1-plus-1-counters`) |
| `name` | CharField | nome exibido (`+1/+1 Counters`) |
| `num_decks` | PositiveIntegerField | do catálogo |
| `popularity_rank` | PositiveIntegerField | posição no catálogo (ordem padrão) |
| `top_commanders` | JSONField | lista ordenada `[{"name", "num_decks"}]`, guardamos até 10, exibimos 3 |
| `art_crop_url` | URLField, blank | art crop do comandante nº 1 (Scryfall) |
| `summary` | CharField(160), blank | resumo pt-BR |
| `summary_model` | CharField, blank | modelo que gerou (ex. `gemini-…`) |
| `summary_generated_at` | DateTimeField, null | |
| `edhrec_synced_at` | DateTimeField, null | última sync bem-sucedida do detalhe |

Temas que somem do catálogo do EDHREC numa sync **não são apagados** (sorteios
antigos apontam para eles); só deixam de ser atualizados. *(Decisão do builder
pode ajustar: um booleano `in_catalog` para tirá-los do sorteio, se preferir.)*

### `apps/core` (escopado por pod)

- `ThemeDraw` — `pod` (FK `pods.Pod`), `created_by` (FK user, null),
  `created_at`.
- `ThemeDrawSeat` — `draw` (FK `ThemeDraw`, related `seats`), `player`
  (FK `Player`), `theme` (FK `cards.Theme`, `PROTECT`), `position`
  (0–3, ordem de exibição). Sem campo `pod`: o pod vem de `draw.pod`.
  `clean()` valida `player.pod_id == draw.pod_id`, como
  `GameParticipant.clean()`. `unique_together` em (`draw`, `player`) e
  (`draw`, `theme`).

Um arquivo por model em `apps/core/models/`, reexportado no `__init__`.

## Regras do sorteio (`DrawThemesUseCase`)

`perform_request(pod, players, created_by) -> ThemeDraw`

- Exatamente 4 jogadores, distintos, todos do `pod` (o form já filtra; o use
  case revalida). **Sempre 4** (confirmado): não construir para N jogadores.
  Pod com menos de 4 jogadores vê uma mensagem de erro no form.
- Temas elegíveis = todos os `Theme` **menos** os já sorteados em
  `ThemeDrawSeat` cujo `draw.pod == pod` e `draw.created_at` está na **semana
  corrente, segunda 00:00 a domingo 23:59 no fuso `America/Sao_Paulo`**.
  O projeto roda com `TIME_ZONE = "UTC"` e isso **não** muda: o fuso é
  aplicado só neste cálculo (constante no use case), para que um sorteio de
  domingo à noite não caia na semana seguinte. *(minha decisão)*
- Sorteia 4 distintos com `random.sample`, sem peso por popularidade.
- Se sobrarem menos de 4 elegíveis (praticamente impossível com 420), ignora a
  regra da semana para completar. *(minha decisão)*
- Cria `ThemeDraw` + 4 `ThemeDrawSeat` numa transação.
- Se o catálogo estiver vazio (comando nunca rodou), o form mostra erro
  amigável "catálogo de temas ainda não foi carregado".

## Resumo do tema (`EnsureThemeSummaryUseCase`)

`perform_request(theme) -> str | None`

- Se `theme.summary` existe, devolve.
- Se não há `GEMINI_API_KEY`, devolve `None` (o app funciona sem LLM).
- Chama o Gemini com prompt **ancorado nos dados**: nome do tema, top
  comandantes (e, se o builder quiser guardar na sync, algumas cartas de alta
  sinergia — só para o prompt, nunca exibidas). Instruções: pt-BR, uma frase,
  no máximo 120 caracteres, explicar como o tema joga/vence, nomes de cartas em
  inglês, não inventar cartas fora das fornecidas.
- Pós-processamento: tira espaços/aspas, e se passar de 120 caracteres corta na
  última palavra inteira e põe "…". Salva `summary`, `summary_model`,
  `summary_generated_at`.
- Timeout curto (~8 s). Qualquer erro (rede, cota, resposta vazia) → loga e
  devolve `None`, sem salvar; a próxima vez que o tema aparecer tenta de novo.
- Duas requisições simultâneas para o mesmo tema podem gerar duas vezes; a
  última grava. Aceitável.

Integração: SDK `google-genai`; config por env `GEMINI_API_KEY` (obrigatória
para ter resumo) e `GEMINI_MODEL` (default: um modelo Flash atual do plano
grátis — confirmar nome e cotas na hora de implementar). A key é uma **API key**
criada no projeto Google Cloud que já existe (habilitar *Generative Language
API*), **não** o client OAuth do login. Adicionar ambos no `.env.example`.

## Sync do catálogo (management command)

`python manage.py sync_edhrec_themes` em `apps/cards/management/commands/`,
rodado manualmente (da máquina do dev apontando para o banco de produção, ou
no shell do Render). Ferramenta de dev/ops.

1. Busca `tags.json`, faz upsert dos 420 temas (`slug`, `name`, `num_decks`,
   `popularity_rank`).
2. Para cada tema, busca `tags/<slug>.json` (≤5 req/s), grava
   `top_commanders` e `edhrec_synced_at`.
3. Para o comandante nº 1, resolve o art crop: procura `Card` por nome exato;
   se não tiver, consulta Scryfall `cards/named?exact=<nome>` e usa
   `image_uris.art_crop` (ou da primeira face). Para pares de partner
   (`"A // B"`), usa a primeira carta.
4. Falha num tema loga e segue; o comando termina com um resumo
   (ok / falhas). Flag `--only <slug>` para depurar um tema. *(minha decisão)*
5. **Não** gera resumos (eles nascem no primeiro sorteio).

## Telas e fluxo

Todas as views herdam `PodMemberRequiredMixin`, são CBVs finas e chamam use
cases. URLs em `apps/core/urls.py`, padrão pt-BR do projeto:

| URL | View | O quê |
|---|---|---|
| `sorteio-de-temas/` | `ThemeDrawCreateView` | form com checkboxes dos jogadores do pod (exatamente 4) + botão "Sortear" → redirect para o detalhe |
| `sorteio-de-temas/<pk>/` | `ThemeDrawDetailView` | um card por jogador + botão "Gerar imagem" |
| `sorteio-de-temas/<pk>/resumo/<theme_id>/` | `ThemeSummaryView` | JSON `{summary: str|null}`; chama `EnsureThemeSummaryUseCase`. Só responde se o tema pertence a um seat do draw (que é do pod) |
| `sorteio-de-temas/<pk>/recap.png` | `ThemeDrawRecapView` | PNG 1080×1350 |

Link "Sorteio de temas" na navbar do pod (`templates/base.html`).

**Card na página de detalhe:** nome do jogador, nome do tema, nº de decks
(formato pt-BR, ex. "62,4 mil decks"), top 3 comandantes, resumo. A página
renderiza na hora com os dados do banco; cada card **sem** resumo dispara um
`fetch` (mesmo estilo do `deck-create-ajax`) ao endpoint de resumo e mostra
"gerando resumo…"; se voltar `null`, o espaço some.

**Compartilhar:** botão "Gerar imagem" busca o PNG; no celular usa a Web Share
API com arquivo (`navigator.share({files})`) quando `navigator.canShare`
aceitar; senão, baixa o arquivo.

## Imagem do recap (`ThemeDrawRecapUseCase`)

Pillow, 1080×1350, fundo escuro, renderizada a cada requisição (o disco do
Render é efêmero; não cachear em arquivo). Layout "A · Lista":

```
┌──────────────────────────────────────────┐
│ [SORTEIO DE TEMAS]   (selo laranja)      │
│ POD <NOME DO POD>                        │
│ ┌──────┬───────────────────────────────┐ │
│ │ art  │ Jogador          62,4 mil decks│ │
│ │ crop │ VOLTRON                        │ │
│ │      │ Top comandante: Cloud, …       │ │
│ │      │ Resumo de até ~120 caracteres  │ │
│ └──────┴───────────────────────────────┘ │
│   … 3 linhas iguais …                    │
│ COMANDÔMETRO              sorteio de temas│
└──────────────────────────────────────────┘
```

- Sem título, sem data, sem cores.
- Art crop baixado do Scryfall na hora, os 4 em paralelo, sob um **prazo
  total de ~10 s** (o gunicorn de produção usa o timeout padrão de 30 s); o
  que não chegar a tempo, ou não existir, vira um bloco de cor sólida neutra.
- A imagem **não chama o Gemini**: usa só os resumos já salvos (a página de
  detalhe já os pediu antes do botão). Seat sem resumo → linha sem o texto.
  *(minha decisão, para a imagem nunca estourar o timeout)*
- Texto quebra em linhas pela largura real (medida com a fonte) e é cortado com
  "…" se não couber.
- Fonte bold livre (OFL), ex. Archivo Black para títulos + Inter para texto,
  em `static/` (ou num diretório de assets da app).
- Mockup aprovado: `.superpowers/brainstorm/…/content/layout-a-v2.html` (local,
  não versionado).

## Dependências e config

- `requirements/base.txt`: `Pillow`, `google-genai`.
- Env: `GEMINI_API_KEY`, `GEMINI_MODEL` (opcional).
- `requests` já existe; o código atual do Scryfall usa `urllib` — o builder
  escolhe, mas mantendo um estilo só dentro de cada cliente.

## Testes

- `DrawThemesUseCase`: 4 distintos; exclui temas da semana corrente do mesmo
  pod; **não** exclui de outro pod nem da semana anterior; fallback quando
  faltam elegíveis; rejeita jogador de outro pod.
- `ThemeDrawSeat.clean()` com jogador de outro pod.
- `EnsureThemeSummaryUseCase` com o cliente Gemini mockado: usa cache, corta
  em 120, erro → `None` sem salvar, sem key → `None`.
- `EdhrecThemeClient`: parsing a partir de fixtures JSON reais salvas
  (um `tags.json` reduzido e um `tags/voltron.json` reduzido).
- Views: não-membro recebe 404; endpoint de resumo recusa tema que não é do
  draw; recap devolve `image/png` 1080×1350 (sem rede: mockar downloads).

## O que fica para o builder

- Nomes finais de templates e CSS (seguir o Tailwind/estilo atual).
- Biblioteca HTTP (`urllib` vs `requests`) e detalhes de retry/rate-limit.
- Escolha exata das fontes e cores do recap, respeitando o mockup.
- Formato de exibição do nº de decks (sugestão: "62,4 mil decks"; abaixo de
  1.000, número cheio).
