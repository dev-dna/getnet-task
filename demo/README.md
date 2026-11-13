# demo/ — gravação do sistema em uso

Não faz parte do serviço (fica fora da imagem Docker). Serve para produzir o vídeo de entrega.

| Arquivo | O que faz |
|---|---|
| `record.py` | Abre o Swagger, executa os cenários contra a API de verdade, filma e monta `out/demo.mp4` |
| `finish.py` | Pega a sua gravação narrada, ajusta o volume, exporta para o YouTube e confere o limite de 15 min |
| `../.claude/skills/ffmpeg-skill/` | Código de terceiros (licença MIT, ver `VENDORED.txt`) que faz a edição de vídeo |

```bash
make demo-setup                       # uma vez: instala o Playwright e o Chromium (precisa do ffmpeg no sistema)
make run                              # terminal 1: sobe a API
make demo                             # terminal 2: grava 9 cenários → demo/out/demo.mp4
python demo/record.py --cases S1,S9   # ou escolha os cenários
python demo/finish.py gravacao.mkv    # sua apresentação narrada → gravacao_youtube.mp4
```

Saídas em `demo/out/`: `demo.mp4`, `demo_contact.png` (12 quadros para conferir), `chapters.txt` (colar na descrição do YouTube) e `results.json` (o que a API respondeu em cada cenário).

A legenda de cada cenário mostra a rota que a API devolveu naquele momento, não a esperada. Se a API estiver com o modelo falso ou com a base de exemplo, o vídeo sai com um aviso fixo na tela.

Sem internet o Swagger não carrega. Nesse caso: `npm pack swagger-ui-dist@5 && tar xzf swagger-ui-dist-*.tgz` e rode com `--swagger-assets package`.
