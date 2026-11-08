# Figures

Every figure in [`docs/images`](../images) is built by one script from documented sources, so each line can be checked and rebuilt.

```bash
cd docs/figures
pip install numpy scipy numba trimesh shapely mapbox_earcut pillow   # and rsvg-convert (librsvg), or: pip install cairosvg
python make_figures.py               # all figures, about a minute
python make_figures.py placement     # just one
```

`extract_reference_data.py` wrote the files in `data/` once (it also needs `mne ezdxf pandas openpyxl networkx`, and downloads the Raspberry Pi drawing, PiEEG's example recording and MakeHuman's base mesh). You only run it again to change a source.

## How the 3D figures are made

FIG. 01, 04 and 05 are renders of real geometry at true scale, not drawings:

- `render3d.py`: a small software renderer. Orthographic camera, soft shadows, ambient occlusion, outlines where one surface passes in front of another. The SVG places the render and draws every label with the same projection, so a leader points at the right millimeter.
- `parts3d.py`: the Raspberry Pi and the PiEEG-8 as solids, Dupont housings, alligator clips, and the cables. A cable is an elastic rod at rest: its own weight against its bending stiffness, nearly inextensible, kept out of the head, the boards and the shelf. The shape is the minimum of that energy. Clips and plugged housings are rigid sections. The bending length of a 26 AWG jumper is taken as 45 mm (a 5 cm end held level barely droops, a 10 cm end hangs down).

| Figure | File | Built from |
|---|---|---|
| Hero | `hero.png` | Bust of Athena: AI generated illustration (Gamma), recolored and cleaned by the script. Trace: a 6 s excerpt of PiEEG's example recording `output3.xlsx`, channel 8, 1 to 40 Hz |
| FIG. 01 System | `system.png` | Head and shoulders from MakeHuman, the boards below, the leads settled by the cable model above. Each lead is a 20 cm jumper plus a 20 cm clip cable |
| FIG. 02 What's in the box | `kit.png` | Raspberry Pi drawing, PiEEG-8 measurements, sticker diameter and cable lengths from the product pages |
| FIG. 03 Mounting | `assembly.png` | Raspberry Pi 3 Model B mechanical drawing (RPI-3B-V1_2, DXF), PiEEG-8 measurements |
| FIG. 04 Electrode placement | `placement.png` | MakeHuman head, MNE-Python standard 10-20 montage fitted to it |
| FIG. 05 Wiring | `wiring.png` | Rendered boards, PiEEG docs (header order), register values written by PiEEG Server 0.49.0, ADS1299 datasheet |
| FIG. 06 Pi header | `header.png` | PiEEG docs (Electrodes & Pinout), PiEEG Server 0.49.0 (`profiles.py`, `hardware.py`), ADS1299 datasheet |

## Measured or approximate

- **Head**: MakeHuman's base mesh (CC0), an average adult, scaled to mm. Nasion to inion over the top: 361 mm.
- **Electrode positions**: MNE-Python's `standard_1020` montage, mapped onto the head by the affine transform that best fits five landmarks (nasion, both preauricular points, inion, Cz), rms 5.5 mm, then moved to the nearest skin point. M1 and M2 are placed by anatomy instead (the template put them under the earlobes): on the mastoid, just behind the lower half of the ear.
- **Raspberry Pi 3 Model B**: outline, parts and the 40 pin header from Raspberry Pi's official DXF drawing. Part heights are typical values, the drawing has none.
- **PiEEG-8**: there is no published mechanical drawing. Outline, holes, electrode header, ADS1299, the four small ICs, LED, tantalum capacitor and jumpers are measured on the top view photo in PiEEG's docs (`pieeg8_led.png`, board printed PiEEG V2.1), about 1 mm accurate. The two columns of small parts beside the electrode header are approximate. The 40 pin socket shares the Pi's coordinates.
- **Stickers**: Somnomedics SEN010C, 26 mm, at true size. Foam thickness and snap stud are approximate.
- **Clips, housings, powerbank, shelf**: typical sizes (alligator clip about 28 mm, Dupont housing 2.54 mm by 14 mm, powerbank 104 by 66 by 16 mm). The coiled Micro USB cable is one possible resting shape of the 1 m cable.
- **Lead paths** quoted in the README (28, 20 and 33 cm sitting) are measured on this head and shoulders model with the board where FIG. 01 shows it.
- **Side views in FIG. 03**: heights are schematic.

## Style

The figures follow the PiEEG Home Lab design system, Lab theme: ground `#0b0d33`, gold for hardware, one fixed color per lead (E1 `#4b4bff`, E2 `#8f96ff` dashed, REF `#22d3ff`, BIAS `#c792ff`), Inter Display, Inter and DejaVu Sans Mono, SVG 1000 px wide, PNG exported at 2x. The real jumpers and clip cables come in rainbow colors; the figures color them by lead.
