# Longboard wall holder

Print **two identical brackets** and space them along the deck length. The longboard stands on its lower edge with the grip tape leaning toward the wall and the bottom/artwork facing outward. The model assumes a 12 kg longboard, a 3× handling factor, and equal load sharing: **176.6 N per bracket**.

- Envelope: 38 × 90 × 32 mm; wall plate, arm, lip, and gusset are all 32 mm wide.
- Cradle opening: 22 mm, narrowing to 19 mm at the retaining bead before padding; suitable for an approximately 12 mm deck.
- Mounting: two support-free M5 diamond clearance holes with 45° countersinks.
- Edge treatment: 1.5 mm external profile fillets, 0.6 mm side-perimeter chamfers, and 45° countersinks.
- Print: PETG, either 32 mm-wide side face on the bed, 6+ walls, 40% gyroid; no supports required.
- Install only into studs or appropriately rated masonry anchors. Add 2–3 mm rubber/cork inside the cradle and on the wall contact points.

`simulation-results.png` shows the actual 2-D SIMP density optimization and linear-static check with the entire deck space enforced as a no-material region. The resulting structure stays below the cradle floor or behind the board. This is concept-stage FEA: printed polymers are anisotropic, creep under sustained load, and vary with printer settings. Proof-load each installed pair to at least 2× the expected board weight over padding before trusting it.
