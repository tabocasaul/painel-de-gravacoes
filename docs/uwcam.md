# uwcam — como o módulo é feito

Sobrescreve, via Magisk, os dois arquivos que o HAL sintético do emulador lê
no boot:

```
/system/vendor/etc/config/emu_camera_back.json
/system/vendor/etc/config/emu_camera_front.json
```

Os originais estão em `docs/emu_camera_{back,front}.original.json`, para
comparação e para reverter.

> **Os originais não são JSON válido.** Ambos têm vírgula sobrando antes do
> `]` em `android.scaler.availableStreamUseCases` (linha 223 do back, 335 do
> front). Não estão corrompidos — vêm assim de fábrica no emulador, cujo
> parser é tolerante. `json.load` e `ConvertFrom-Json` recusam os dois; se for
> processar por script, tire as vírgulas antes. Os dois arquivos **do módulo**
> são JSON estrito e passam sem ajuste.

## O truque: a frontal já era multi-camera

O emulador **não** vem com uma traseira multi-camera para copiar. Mas vem com
uma **frontal**:

| arquivo stock | formato | físicas |
|---|---|---|
| `emu_camera_front.json` | array de 3 entradas | ✅ `physicalIds` |
| `emu_camera_back.json`  | objeto único | ❌ nenhuma |

Então o módulo **troca os dois de lado**. A traseira do módulo é o JSON da
frontal original, com três edições:

1. `android.lens.facing`: `FRONT` → `BACK` (nas 3 entradas)
2. `android.sensor.orientation`: `270` → `90` (nas 3 entradas)
3. na **terceira** entrada (a física `4`), a lente vira ultra-wide:

   | | stock (frontal) | módulo |
   |---|---|---|
   | `lens.info.availableFocalLengths` | `4.38 mm` | **`1.70 mm`** |
   | `sensor.info.physicalSize` | `5.6448 × 4.2336 mm` | **`4.656 × 3.496 mm`** |
   | FOV diagonal resultante | ≈ 77,7° | **≈ 119,4°** |

   `FOV = 2·atan(diagonal_do_sensor / 2·focal)`, com
   `diagonal = √(4.656² + 3.496²) = 5.8224 mm` → `2·atan(5.8224/3.4) = 119,4°`.

É esse 119,4° que satisfaz o `EgoCameraController.resolveUltraWide` do Minute
e faz a gravação liberar.

### Os IDs das físicas

`android.logicalMultiCamera.physicalIds` guarda os IDs como bytes, não como
texto:

```json
["51", "0", "52", "0"]
```

`51` e `52` são os códigos ASCII de `'3'` e `'4'`, cada um terminado em `0`.
Ou seja, as físicas são **`3`** (wide, entrada 2) e **`4`** (ultra-wide,
entrada 3) — daí o `ultraWide=4` que aparece no log do Minute.

Esses valores vieram intactos da frontal original; o módulo não os alterou.

## ⚠️ Efeito colateral: a frontal perde as físicas

A troca é simétrica: a **frontal** do módulo é o JSON da traseira original —
uma câmera simples, sem `physicalIds`, sem `LOGICAL_MULTI_CAMERA`.

Para este projeto isso não importa (o Minute só usa a traseira), mas se você
depender da frontal como multi-camera lógica, ela **não é mais**. Nesse caso,
mantenha a frontal original em vez da do módulo:

```bash
adb push docs/emu_camera_front.original.json \
    /data/adb/modules/uwcam/system/vendor/etc/config/emu_camera_front.json
adb reboot
```

Mas aí você fica com físicas na frontal **e** na traseira ao mesmo tempo — não
foi testado se o HAL sintético aguenta as duas.

## Conferir se pegou

Com o emulador subido com `-camera-back emulated`:

```bash
adb shell "dumpsys media.camera | grep -E 'Facing|physicalIds'"
```

A traseira tem que aparecer com `physicalIds`. Se aparecer sem, o emulador
subiu com fonte `webcam`/`videofile:` — essas usam o HAL legacy, que não lê
estes JSONs e não tem físicas. Ver §6 do README principal.
