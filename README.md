# H-Line Station

One window that replaces Stellarium + SDR# + the IF Average plugin for hydrogen-line
outreach with a Discovery Dish and an RTL-SDR dongle.

* **Left:** an all-sky dome of the sky above the site (stars, constellations, planets,
  Sun and Moon, the Milky Way glow and the galactic plane). The dish beam is shown as a green circle,
  and a dotted track shows which sky will drift into the beam over the next few hours.
* **Top right:** where the dish is looking (constellation, galactic l/b, RA/Dec, LSR correction),
  receiver status, and a top-down Milky Way map with the line of sight. Detected hydrogen
  clouds are placed at their kinematic distance.
* **Bottom right:** the averaged 21 cm spectrum. Velocity relative to the LSR is on the bottom
  axis and observed frequency in MHz on the top axis. Hydrogen peaks are marked automatically.
* **Outreach mode (F11):** full screen, larger text, plus plain-language captions
  ("We are detecting 3 clouds of hydrogen gas: 64 km/s toward us, about 31,000 light-years away…")
  and rotating facts about the 21 cm line.

## Quick start (Windows 10/11)

1. Unzip the folder anywhere, for example `Documents\HLineStation`.
2. **Close SDR#.** Only one program can use the dongle at a time.
3. Double-click **`Run-HLineStation.bat`**.
   The first run sets up Python and the libraries, which takes 2–3 minutes and needs internet.
   If Python isn't installed, the script installs it with winget; run the script again afterwards.
4. Open **⚙ Settings → Site** and enter your club's latitude and longitude.
   The defaults are for the Alton/Riverbend area.
5. Set the dish **Az/El** in the toolbar, or double-click a spot on the sky map.

The other launchers:

* `Run-Outreach-Mode.bat` starts straight in full-screen outreach mode.
* `Run-Demo-Simulator.bat` runs with simulated data, so you can practise without the dish.
  Simulated data is always labelled **SIMULATED DATA** on screen.

The RTL-SDR uses the same WinUSB (Zadig) driver as SDR#, so nothing extra is needed. The included
`drivers\rtlsdr.dll` is the RTL-SDR Blog build, which supports V3 and V4 dongles and the bias-tee.

## Keys

| Key | Action |
|---|---|
| F11 | Outreach (full-screen) mode on/off |
| Esc | Leave outreach mode |
| Space | Start/stop the receiver |
| R | Restart the average |
| A | Auto background |
| B | Capture background |
| S or F12 | Snapshot (PNG + CSV) to `Documents\HLineStation Snapshots` |

## Getting a clean spectrum

Every receiver is more sensitive at some frequencies than others. That shape has to be divided
out, or it shows up as a big fake hump. There are three ways to do it:

* **★ Auto background** (recommended, key A) needs no dish movement.
  1. Let the receiver run, then click **★ Auto background**.
  2. For about a minute the receiver tunes 2.5 MHz above and then below the hydrogen line, so
     it hears only its own empty band, and records that shape. Then it tunes back.
  3. The program switches to "Background + baseline". The background is saved and reused at
     later events. Run it again if you change the gain, the frequency or the sample rate.
* **Auto baseline** (used until a background exists) fits a smooth curve to the edges of the band,
  outside ±150 km/s, and divides it out. Narrow interference spikes are ignored by the fit, and the
  fit always uses the same receiver frequencies, so re-aiming the dish never changes the hump height.
* **Capture background** (key B) saves the current average as the reference. It's like
  *Acq. backgr.* in the IF Average plugin, but only useful when the beam is far from the Milky Way.

**Interference spikes** – narrow spikes a few km/s wide are local radio interference (computer, USB,
chargers). The program removes anything narrower than 5 km/s that sticks up well above the noise
and replaces it with the surrounding level; real hydrogen is always wider than that, so it's left
alone. Removed spots are shaded orange on the graph (not in outreach mode) and counted in the title.
Turn it off or change the width in Settings → Processing. Moving the dongle away from the PC with a
USB extension cable still helps, since removal can't recover a signal hidden under a spike.

**Smoothing** – 4 km/s by default. Each channel is only 0.25 km/s wide, far narrower than any
hydrogen feature, so averaging neighbouring channels cuts the noise about 4× without changing the
shape of the hydrogen. 3–5 km/s is the sweet spot; above ~10 km/s narrow peaks start to get
flattened and look lower than they really are.

The averaging time, smoothing, line window, band trim, peak threshold and Auto background
offset/duration are in Settings → Processing.

## Graph scale and the SDR#-style view

* **🔒 Lock scale** (toolbar, key L) freezes the vertical scale at whatever you see when you click it.
  The graph then stops auto-zooming: noise looks small and the hydrogen bump visibly rises and falls
  as the Milky Way drifts through the beam. Exact limits (default −5 % to +40 %) are in
  Settings → Display. Outreach mode always uses the locked scale unless you turn that off.
* **SDR#-style** (Processing box) shows raw power in dB across the whole band with the receiver's
  shape left in, on a fixed 4 dB-tall scale, just like the IF Average window.
* **FFT size 256** (Settings → Receiver) matches IF Average's "FFT resolution 256": about 2 km/s
  per point instead of 0.25 km/s. Coarser, but less fine fuzz.

## Receiver notes

* **Defaults:** centre 1420.40575 MHz, 2.4 MS/s, 2048-point FFT (about 0.5 km/s per bin),
  gain 40.2 dB. The centre (DC) spike of the RTL-SDR is removed automatically.
* **Bias-tee is ON by default** to power the Discovery Dish feed/LNA. Turn it off in
  Settings → Receiver if you power the feed some other way.
* **"No RTL-SDR dongle found" or "could not open":** close SDR#, then unplug and replug the dongle.

## Making a stand-alone .exe

After running `Run-HLineStation.bat` once, double-click **`Build-EXE.bat`**. It creates
`dist\HLineStation\HLineStation.exe`. Copy that whole folder to the outreach laptop; it does not
need Python.

## How it works and its limits

* Velocities use the radio convention and are corrected to the LSR (standard solar motion,
  20 km/s). The correction matches astropy's LSRK to within 0.01 km/s.
* Distances on the Milky Way map are kinematic. They assume a flat rotation curve with
  R0 = 8.15 kpc and V0 = 236 km/s (Reid et al. 2019), so treat them as illustrations, not
  measurements. They are only shown when the beam is within 15° of the galactic plane.
  * Toward l < 90° or l > 270°, there are two possible distances. These are drawn as hollow circles.
  * Velocities near 0 km/s are labelled as local gas.
* The spiral arms on the map are a schematic four-arm logarithmic spiral.
* The y-axis shows percent above the background. It is not calibrated in kelvin.

## Credits

* Star, constellation and name data: [d3-celestial](https://github.com/ofrohn/d3-celestial) by
  Olaf Frohn (BSD-3-Clause, see `data/LICENSE-d3-celestial.txt`).
* `drivers/rtlsdr.dll`: [RTL-SDR Blog driver](https://github.com/rtlsdrblog/rtl-sdr-blog)
  (GPL-2.0; source code at that link).
* Built with PySide6 (Qt), pyqtgraph, NumPy, PyEphem and pyerfa.
