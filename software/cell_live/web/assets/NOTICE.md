# Notices for the console's assets

## Fonts (shipped in `fonts/`)

The page loads no font from the internet. The seven `.woff2` files below are the Latin subset,
taken from the `@fontsource` packages (version 5.3.0) of each family. Every family is licensed
under the SIL Open Font License 1.1. The full text and the copyright line of each family are in
the `LICENSE-*.txt` file next to the fonts. Keep those files with the fonts when you copy them.

| Family | Weights used | Where it is used | Licence file |
|---|---|---|---|
| Atkinson Hyperlegible Next | 400, 600, 800 | all text | `fonts/LICENSE-Atkinson-Hyperlegible-Next.txt` |
| Atkinson Hyperlegible Mono | 400, 700 | numbers, times, raw replies (tabular figures) | `fonts/LICENSE-Atkinson-Hyperlegible-Mono.txt` |
| Big Shoulders Display | 700, 900 | titles and the run-state word only | `fonts/LICENSE-Big-Shoulders-Display.txt` |

The Big Shoulders licence file starts with the copyright line from the upstream project
(`xotypeco/big_shoulders`). The `@fontsource` package only had a placeholder line there.

The Latin subset has no arrows, ticks or round bullets. The lamps are drawn in CSS and the few
arrows that appear in help text fall back to the system font.

## Ideas, not code

These sites gave ideas for the design. The console is plain HTML, CSS and JavaScript with no build
step, and those sites ship React and Tailwind components, so nothing was installed or copied.
Everything was written again from the idea.

| Site | Idea that was reused | Licence on the site when checked (16 Nov 2026) |
|---|---|---|
| magicui.design | A pulse that travels along a line between two boxes (Animated Beam): the cell map pulse | MIT for the free components, Pro components are paid |
| uiverse.io | A small lamp that changes shape with its state, and a switch drawn on a checkbox | MIT unless the element says otherwise |
| reactbits.dev | Numbers that settle when a value changes, and step indicators | MIT with the Commons Clause |
| 21st.dev | A confirm dialog and a toast in the shadcn style | Each component has its own licence |
| mobbin.com | Reference screenshots only | Not reusable |

If you paste a snippet from any of these sites into the console later, add a row here first: the
site, the component name, the link and the licence you read on that page that day. Check the
licence again at that time. This table is not a licence check.
