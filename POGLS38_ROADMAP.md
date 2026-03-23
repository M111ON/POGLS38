# POGLS38 Master Roadmap
# สถานะ: 2026-03-22 | 815/815 tests pass

## ✅ DONE — Foundation (Session 1-N)

### Layer 0: Math & Geometry
- [x] 17n Lattice (289 cells, 17×17 torus)
- [x] PHI constants (PHI_UP, PHI_DOWN, PHI_SCALE)
- [x] QuadFibo audit (X+(-X)=PHI_SCALE invariant)
- [x] Morton encode (spatial locality)
- [x] World 3 math: n×72 : 72 : 17n (documented, not coded yet)

### Layer 1: Storage & Repair
- [x] DiamondBlock 64B (XOR guard, HoneycombSlot)
- [x] ShellN n=4..16 (replaces fixed World 4n/5n/6n)
- [x] Delta lanes X/-X/Y/-Y (PHI scatter routing, CRC32)
- [x] P→P→R→E repair pipeline (ScaleLadder, WorldFlip, Recycle)

### Layer 2: Observers
- [x] Tails (read-only, summon-only, NegativeShadow emergency key)
- [x] Entangle + WarpDetach (hibernate/wake, warp bridge)
- [x] Tentacle (MPMC queue, Detach activate)
- [x] Bitboard 289-node + Frontier diffuse

### Layer 3: Temporal
- [x] FiftyFourBridge ring[256] + hash[1024]
- [x] NegativeShadow pool (evicted entries, Tails emergency key)
- [x] InvertedTimeline (head-- backward audit)
- [x] XOR double guard (g0, g1=g0^PHI_DOWN)
- [x] World 4n/5n/6n + seal/verify

### Layer 4: Scheduling
- [x] Hydra 16-head SPSC + work steal
- [x] Voronoi routing (4×4 centroid grid, 289 cells)
- [x] Delaunay boundary steal (near-boundary detection)
- [x] 2-Phase hybrid engine (fast path O(1) + slow path amortized)
- [x] Sleep wire (energy model, gate_18 wake)
- [x] Field pressure (load-aware routing)
- [x] Hysteresis (anti flip-flop)
- [x] Resource-aware spawn (OS load, mem check)
- [x] Cooldown = 162 events (NODE_MAX, 9×gate_18)
- [x] Max 2 heads on split, unlock to 16 later

### Layer 5: Engine
- [x] l38_write() 8-step pipeline entry point
- [x] l38_engine_init() all subsystems wired

---

## 🔄 IN PROGRESS — Next Sessions

### Phase A: World 3 Ring (GPU temporal, priority)
**Concept:**
  n×(8×9) : 72 : (8n+9n)
  72 = LCM(2³,3²) = GPU block size
  17n = CPU inner lattice
  34n+1 mod 17 = 1 always → isolation guarantee

**Tasks:**
- [ ] A1: `pogls_38_world3.h`
      - W3Ring: ring[72n] flexible (n=4..72)
      - 34n+1 addressing (stride=34, phase_offset=1)
      - GPU block: dim_x=8, dim_y=9 → 72 threads
      - gate_17: every write is gate event (34n+1 mod 17 = 1)
- [ ] A2: W3Ring ↔ FiftyFourBridge bridge
      - recall_tag from W3 → FiftyFourBridge lookup
      - evict from W3 → NegShadow in Temporal
- [ ] A3: CUDA kernel stub (GTX 1050Ti, SM 6.1)
      - dim3 block(8,9) = 72 threads
      - stride=34 addressing
      - shared mem for W3 ring slice

### Phase B: Tails Pointer + DNA
**Concept from g7b:**
  sig_fast (CRC32 on StateR) = recall_tag pattern
  AssociativeCache = L2 pattern (already in FiftyFourBridge)
  RewindBuffer = V4 rewind (need to port)

**Tasks:**
- [ ] B1: `pogls_38_dna.h`
      - DNA entries: Tails tracks permutation chain
      - StateR-like: 6×64 bit Rubik-Hilbert state
      - sig_fast pattern: CRC32 → recall_tag
- [ ] B2: RewindBuffer port
      - ring[972] = 54×18 slots (sacred number)
      - undo chain: Rubik inverse sequence
- [ ] B3: g7b AssociativeCache → L2 layer in FiftyFourBridge
      - 4-way 64-set (burst hit 99%)
      - replaces current simple hash index

### Phase C: Engine Bridge (G4c Memory Fabric)
- [ ] C1: POST /remember → l38_write() → World6n
- [ ] C2: GET /recall → Tails summon → FiftyFourBridge recall
- [ ] C3: World 3 as outer container for Memory Fabric
      - W3 ring wraps World 6n sessions
      - no sync needed (local, Rubik state self-consistent)

### Phase D: Split World (แยกร่าง)
- [ ] D1: DetachFrame → spawn ≤2 heads
- [ ] D2: World A thread (CPU, binary) ↔ World B thread (CPU/GPU, ternary)
- [ ] D3: gate_17 sync point (W3 boundary)
- [ ] D4: rejoin: merge split heads back to base

### Phase E: GPU Full Path
- [ ] E1: CUDA fold audit (fold_batch_verify on GTX 1050Ti)
- [ ] E2: W3 GPU producer → CPU ring consumer
- [ ] E3: AVX2 + CUDA combined benchmark
- [ ] E4: bench on Colab T4 / Kaggle P100

### Phase F: GUI + External
- [ ] F1: G4b: tab_files/tab_hydra → EngineBridge hook
- [ ] F2: binary-index.js → L38TailsCheckpoint wire
- [ ] F3: Cowork integration

---

## 📐 Sacred Numbers (FROZEN)

| Number | Meaning |
|--------|---------|
| 17 | gate, bridge, prime |
| 18 | gate_18 = internal clock |
| 34 | 2×17 = Fib(9) = World 3 stride |
| 54 | 2×3³ = FiftyFourBridge nexus |
| 55 | Fib(10) = W3-W12 gap |
| 72 | LCM(8,9) = GPU block = base-72 |
| 144 | Fib(12) = active cells |
| 162 | NODE_MAX = 3⁴×2 = full icosphere |
| 289 | 17² = 17n lattice cells |
| 648 | Shell(4) = W3(n=9) |

## 🔒 Rules (FROZEN)

1. 16 heads MAX (32 = overflow, proven)
2. Split world = max 2 heads until GPU ready
3. Cooldown = 162 events before next spawn
4. 34n+1 mod17 = 1 always (W3 isolation)
5. Tails = read-only + summon only
6. DiamondBlock = 64B, cache-line aligned
7. delta commit only at gate_18 or audit pass

---

## 💡 Key Insights (จด ไม่ลืม)

- g7b Rubik-Hilbert: burst hit 99% → no sync needed
  → World 3 temporal ring concept verified
- 72/17 = constant expansion ratio (4.235x)
- 72-17 = 55 = Fib(10) = GPU exclusive zone
- Energy model > idle_ticks (smooth, no oscillation)
- "event = cheap, control = amortized" (2-phase rule)
- Voronoi max 8.7% per head vs greedy 88.6%
- NegativeShadow = "negative ของ pointer" (Tails emergency key)
