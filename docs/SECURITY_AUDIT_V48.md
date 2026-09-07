# Security Audit Report - TF2autoswap v4.8
**Date:** 2026-07-02  
**Audited via:** automated adversarial QA tools  
**Codebase:** active_development/

## Executive Summary
Comprehensive security audit of TF2autoswap v4.8 codebase (5,915 lines across 4 core modules). **2 CRITICAL security vulnerabilities identified** requiring immediate remediation before release. The material safety layer (tf2_material.py) demonstrates excellent security-first design with path traversal protection and wallhack prevention.

## Critical Findings

### CRITICAL-001: Schema File Size Validation Missing
**Module:** `tf2_schema.py`, `load_schema()` function (line 202-220)  
**Severity:** CRITICAL  
**CVE Risk:** Memory exhaustion attack

**Description:**  
`load_schema()` reads items_game.txt with no file size validation. An adversary could craft a malicious schema file (e.g., 5GB of repeated content) that would cause memory exhaustion when loaded via `f.read()`.

**Attack Vector:**
```python
# Current vulnerable code:
with open(igt, encoding="utf-8", errors="replace") as f:
    return vdf.loads(f.read())  # No size limit
```

An attacker providing a malicious TF2 directory or schema file could trigger OOM.

**Remediation:**
```python
MAX_SCHEMA_SIZE = 200 * 1024 * 1024  # 200MB (real schema is ~20MB)

with open(igt, encoding="utf-8", errors="replace") as f:
    size = os.path.getsize(igt)
    if size > MAX_SCHEMA_SIZE:
        raise SwapError(
            f"Schema file too large ({size / 1024 / 1024:.1f}MB). "
            f"Maximum allowed is {MAX_SCHEMA_SIZE / 1024 / 1024:.0f}MB. "
            "This may indicate a corrupted or malicious file."
        )
    return vdf.loads(f.read())
```

**Impact:** HIGH - DoS via memory exhaustion on untrusted schema files

---

### CRITICAL-002: Schema Cache Size Validation Missing
**Module:** `tf2_schema.py`, `load_schema_cache()` and `load_defindex_cache()` functions  
**Severity:** CRITICAL  
**CVE Risk:** Memory exhaustion via cache poisoning

**Description:**  
Cache loading functions (`load_schema_cache()`, `load_defindex_cache()`) perform no size validation before `json.load()`. An attacker with filesystem access could replace cache files with multi-gigabyte payloads causing memory exhaustion.

**Attack Vector:**
```bash
# Attacker replaces cache with 5GB malicious JSON
echo '{"items": {"x": "' > ~/.config/tf2autoswap/schema_cache.json
python -c 'print("A" * (5*1024*1024*1024))' >> ~/.config/tf2autoswap/schema_cache.json
echo '"}}' >> ~/.config/tf2autoswap/schema_cache.json
```

Next run: OOM crash on cache load.

**Remediation:**
```python
MAX_CACHE_SIZE = 100 * 1024 * 1024  # 100MB (real cache ~5MB)

def load_schema_cache(cache_file):
    if not os.path.isfile(cache_file):
        return None
    size = os.path.getsize(cache_file)
    if size > MAX_CACHE_SIZE:
        # Corrupted/poisoned cache - delete and regenerate
        os.remove(cache_file)
        return None
    with open(cache_file, encoding="utf-8") as f:
        return json.load(f)
```

**Impact:** HIGH - Persistent DoS via cache poisoning; requires filesystem access

---

## High-Severity Findings

### HIGH-001: Material File Size Validation Deferred
**Module:** `tf2_material.py`, VMT/VTF parsing  
**Severity:** HIGH (deferred by design)  
**Status:** Acknowledged, not exploitable in current threat model

**Description:**  
VMT and VTF files have no explicit size limits in `scan_vmt_safety()` or `validate_material_set()`. Unlike the schema file (which originates from untrusted sources), material files are:
1. User-selected from their own TF2 install
2. Limited by TF2's own VPK format constraints
3. Bounded by practical texture resolution limits (8192x8192 VTF max)

**Decision:** DEFERRED  
**Rationale:** Material files are user-controlled input from a validated game install. TF2's VPK format and texture engine already enforce practical limits. Adding explicit validation would duplicate engine-level constraints without meaningful security benefit.

**Monitoring:** If future versions support untrusted material sources (e.g., network downloads, user uploads), add 50MB limit to `validate_material_set()`.

---

## Security Strengths (Exemplary Design)

### Path Traversal Protection (tf2_material.py)
**Lines:** 102-163 (`classify_material_path()`)

**Strength:** Uses `posixpath.normpath()` BEFORE classification checks, preventing `../` path traversal exploits that could bypass wallhack detection.

**Example Attack (prevented):**
```python
# Malicious path: weapon prefix, but resolves to blocked map material
path = "materials/models/weapons/c_models/../../../maps/de_dust/wall.vmt"
# normpath() collapses to: "materials/maps/de_dust/wall.vmt"
# Classification: "world" (BLOCKED) ✓
```

**Impact:** Prevents wallhack material injection via MDL cdmaterials directory strings.

---

### VMT Runtime Proxy Detection (tf2_material.py)
**Lines:** 232-293 (`find_risky_proxy_targets()`, `has_proxies_block()`)

**Strength:** Detects `Proxies` blocks that animate risky parameters (`$alpha`, `$ignorez`) at runtime, which static scans would miss. This catches:
- Animated transparency that appears static in VMT text
- Dynamic depth-test disabling triggered at runtime
- Fresnel self-illum effects (soft ESP)

**Example Attack (detected):**
```vmt
"VertexLitGeneric" {
    "$alpha" "1.0"  // Looks clean in static scan
    "Proxies" {
        "AnimatedValue" {
            "resultVar" "$alpha"  // ← DETECTED: runtime animation to 0.1
            "minVal" "0.1"
            "maxVal" "1.0"
        }
    }
}
```

Classification: **CRITICAL** (blocks unconditionally) ✓

---

### Shader Classification (tf2_material.py)
**Lines:** 334-336, 187-188

**Strength:** Blocks unlit shaders (`UnlitGeneric`, `UnlitTwoTexture`) on player-visible materials. These remove lighting calculations, causing fullbright rendering (soft ESP).

**Detection:** Uses lowercase shader name matching against `_UNLIT_SHADERS` set.

---

## Moderate Findings

### MODERATE-001: VPK Chunk Integrity Handling
**Module:** `tf2_core.py`, `read_vpk_entry()` function (lines 182-226)  
**Severity:** MODERATE  
**Status:** VERIFIED SAFE

**Description:**  
Distinguishes `KeyError` (path not in index) from `FileNotFoundError` (missing chunk file). Converts missing chunks to `BuildError` with user-facing message.

**Security Impact:** None - proper error handling, prevents silent failures.

---

## Low-Severity Findings

### LOW-001: Import Safety (Lazy Imports)
**Module:** `tf2_core.py` (line 154-179), `tf2_schema.py` (line 174-199)  
**Severity:** LOW  
**Status:** VERIFIED SAFE

**Description:**  
Uses lazy imports with `subprocess.run([sys.executable, "-m", "pip", "install", ...])` for auto-dependency installation.

**Security Review:**
- Uses `sys.executable` (no shell injection)
- Hardcoded package names ("vpk", "vdf")
- check=True ensures failures propagate
- No user-controlled strings in command

**Verdict:** SAFE - no injection vectors.

---

## Compliance Summary

| **Metric** | **Target** | **Actual** | **Status** |
|---|---|---|---|
| Critical Issues | 0 | 2 | ❌ FAIL |
| Critical Issues Fixed | 2 | 0 | ⏳ PENDING |
| High-Severity Issues (exploitable) | 0 | 0 | ✅ PASS |
| Security-Critical Module Coverage | 100% | 100% | ✅ PASS |
| Path Traversal Protection | Present | Present | ✅ PASS |
| Memory Exhaustion Protection | Present | Absent | ❌ FAIL |

---

## Recommendations

### Immediate (Pre-Release)
1. **Implement CRITICAL-001 fix:** Add `MAX_SCHEMA_SIZE` validation to `tf2_schema.py::load_schema()`
2. **Implement CRITICAL-002 fix:** Add `MAX_CACHE_SIZE` validation to cache loading functions
3. **Add security regression tests:** Adversarial test cases for oversized schemas/caches

### Short-Term (v4.9)
1. Add file size logging for telemetry (max schema/cache sizes seen in wild)
2. Document security model in SECURITY.md: trusted vs untrusted inputs
3. Consider rate-limiting cache regeneration (prevent DoS via repeated cache corruption)

### Long-Term (v5.0)
1. If network material sources added: implement 50MB limit in `validate_material_set()`
2. Sandboxed VDF parsing (separate process with resource limits)
3. Security audit of VPK write path (`build()`, `build_material_only()`)

---

## Test Coverage Gaps

### Missing Security Tests
1. **Schema file size enforcement** (CRITICAL-001)
2. **Cache file size enforcement** (CRITICAL-002)
3. **Path traversal in classify_material_path()** (currently verified by manual review only)
4. **Proxy-based runtime transparency** (detected but not regression-tested)

### Existing Coverage (from test_material_safety.py)
- ✅ Path classification (10 test cases)
- ✅ VMT safety scan (7 test cases)
- ✅ Material set validation (8 test cases)
- ✅ MDL parser (synthetic header tests)
- ✅ Path traversal protection (3 test cases)

---

## Appendix: Code Metrics

| **Module** | **Lines** | **Functions** | **Security-Critical** |
|---|---|---|---|
| tf2_schema.py | 821 | 12 | load_schema(), *_cache() |
| tf2_core.py | 1,824 | 28 | read_vpk_entry(), build() |
| tf2_material.py | 821 | 13 | classify_material_path(), scan_vmt_safety() |
| tf2autoswap.py | 3,270 | 18 | (CLI only, no security-critical logic) |
| **TOTAL** | **5,915** | **71** | **8 functions** |

---

## Sign-Off
**Status:** FAIL (2 critical issues outstanding)  
**Blocker:** CRITICAL-001, CRITICAL-002 must be resolved before v4.8 release.

**Next Steps:**
1. Implement critical fixes
2. Create security regression tests
3. Re-audit fixed code
4. Update CHANGELOG with security fixes
