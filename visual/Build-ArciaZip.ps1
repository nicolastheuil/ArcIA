# ==============================================================================
# GÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°NÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°RATEUR D'ARCHIVE ZIP COMPLÃƒÆ’Ã†â€™Ãƒâ€¹Ã¢â‚¬Â TE ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ARCITEK ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â ARCIA (20 FICHIERS + ASSETS)
# CrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©e ./arcia-complete-pack/ et ./arcia-complete-pack.zip
# ==============================================================================
$ErrorActionPreference = "Stop"
$OutRoot = Join-Path $PWD "arcia-complete-pack"
$ZipPath = Join-Path $PWD "arcia-complete-pack.zip"

if (Test-Path $OutRoot) { Remove-Item $OutRoot -Recurse -Force }
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }

function Write-Utf8File([string]$RelPath, [string]$Content) {$FullPath = Join-Path $OutRoot $RelPath
    $Dir = Split-Path $FullPath -Parent
    if (-not (Test-Path $Dir)) { New-Item -ItemType Directory -Path $Dir -Force | Out-Null }
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($FullPath, $Content.TrimStart(),$Utf8NoBom)
    Write-Host "  [+] GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© : $RelPath" -ForegroundColor Cyan
}

Write-Host "`n[1/4] GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ration des 8 fichiers vectoriels SVG (Logos, Mascottes Arci'Bots, Planche MaÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â®tresse)..." -ForegroundColor Yellow

# 1. LOGO ARCITEK.SVG
Write-Utf8File "assets/branding/logo-arcitek.svg" @'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 140" width="420" height="140" fill="none">
  <defs>
    <linearGradient id="arc-cyan" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#2CE5F2" />
      <stop offset="100%" stop-color="#00C8D7" />
    </linearGradient>
  </defs>
  <rect width="420" height="140" rx="20" fill="#0D254C" />
  <path d="M36 74 C 58 22, 145 14, 196 46" stroke="url(#arc-cyan)" stroke-width="7" stroke-linecap="round" fill="none" />
  <circle cx="196" cy="46" r="8" fill="#FACC15" />
  <text x="42" y="102" font-family="Plus Jakarta Sans, Inter, Segoe UI, sans-serif" font-size="76" font-weight="800" letter-spacing="-1.5">
    <tspan fill="#F8FAFC">arci</tspan><tspan fill="#00C8D7">Tek</tspan>
  </text>
</svg>
'@

# 2. LOGO ARCIA.SVG
Write-Utf8File "assets/branding/logo-arcia.svg" @'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 460 140" width="460" height="140" fill="none">
  <defs>
    <linearGradient id="bot-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2CE5F2" />
      <stop offset="60%" stop-color="#00C8D7" />
      <stop offset="100%" stop-color="#0891B2" />
    </linearGradient>
  </defs>
  <rect width="460" height="140" rx="20" fill="#0D254C" />
  <g transform="translate(26, 20)">
    <path d="M8 92 V 50 C 8 22, 30 6, 54 6 C 78 6, 100 22, 100 50 V 92" stroke="url(#bot-grad)" stroke-width="6.5" stroke-linecap="round" fill="none" />
    <line x1="54" y1="6" x2="54" y2="-6" stroke="#00C8D7" stroke-width="4" stroke-linecap="round" />
    <circle cx="54" cy="-9" r="6" fill="#FACC15" />
    <rect x="24" y="28" width="60" height="42" rx="21" fill="url(#bot-grad)" />
    <rect x="32" y="37" width="44" height="24" rx="12" fill="#111C44" />
    <ellipse cx="44" cy="49" rx="3.5" ry="5" fill="#FACC15" />
    <ellipse cx="64" cy="49" rx="3.5" ry="5" fill="#FACC15" />
    <path d="M48 55 Q 54 61 60 55" stroke="#FACC15" stroke-width="2.5" stroke-linecap="round" fill="none" />
    <path d="M36 82 H 72" stroke="#00C8D7" stroke-width="4" stroke-linecap="round" />
    <path d="M44 91 H 64" stroke="#FACC15" stroke-width="3" stroke-linecap="round" />
  </g>
  <text x="150" y="88" font-family="Plus Jakarta Sans, Inter, Segoe UI, sans-serif" font-size="72" font-weight="800" letter-spacing="-1">
    <tspan fill="#F8FAFC">Arc</tspan><tspan fill="#00C8D7">I</tspan><tspan fill="#FACC15">A</tspan>
  </text>
  <text x="154" y="114" fill="#94A3B8" font-family="JetBrains Mono, monospace" font-size="13" font-weight="600">
    PLATEFORME AGENTIQUE D'ENTREPRISE
  </text>
</svg>
'@

# 3. MASCOTTE 1 : BOT-WELCOME.SVG
Write-Utf8File "assets/branding/bot-welcome.svg" @'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 360" width="300" height="360" fill="none">
  <defs>
    <linearGradient id="body-cyan" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2CE5F2" />
      <stop offset="60%" stop-color="#00C8D7" />
      <stop offset="100%" stop-color="#0891B2" />
    </linearGradient>
    <linearGradient id="sign-gold" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FDE047" />
      <stop offset="100%" stop-color="#F59E0B" />
    </linearGradient>
  </defs>
  <rect width="300" height="360" rx="28" fill="#F0F7FF" />
  <polygon points="45,78 75,88 52,102" fill="#FACC15" />
  <polygon points="34,114 66,118 40,132" fill="#FACC15" />
  <polygon points="255,78 225,88 248,102" fill="#FACC15" />
  <polygon points="266,114 234,118 260,132" fill="#FACC15" />
  <path d="M142 74 L150 42 L158 74 Z" fill="#111C44" />
  <circle cx="150" cy="36" r="11" fill="url(#sign-gold)" />
  <path d="M82 140 C82 84, 218 84, 218 140 C218 158, 82 158, 82 140 Z" fill="url(#body-cyan)" stroke="#0891B2" stroke-width="2.5" />
  <rect x="100" y="100" width="100" height="44" rx="20" fill="#111C44" />
  <ellipse cx="126" cy="120" rx="4.5" ry="7" fill="#FACC15" />
  <ellipse cx="174" cy="120" rx="4.5" ry="7" fill="#FACC15" />
  <path d="M136 125 Q150 140 164 125 Z" fill="#FACC15" />
  <ellipse cx="150" cy="176" rx="58" ry="13" fill="#111C44" />
  <path d="M78 184 C72 264, 100 304, 150 304 C200 304, 228 264, 222 184 Z" fill="url(#body-cyan)" />
  <rect x="64" y="202" width="172" height="58" rx="12" fill="url(#sign-gold)" stroke="#EAB308" stroke-width="2.5" transform="rotate(-3 150 231)" />
  <text x="150" y="239" text-anchor="middle" fill="#111C44" font-family="Plus Jakarta Sans, Inter, sans-serif" font-size="27" font-weight="900" transform="rotate(-3 150 231)">
    WELCOME
  </text>
  <circle cx="66" cy="236" r="17" fill="#111C44" />
  <circle cx="234" cy="228" r="17" fill="#111C44" />
  <ellipse cx="150" cy="324" rx="34" ry="7" fill="#00C8D7" />
  <ellipse cx="150" cy="342" rx="22" ry="5" fill="#0891B2" />
</svg>
'@

# 4. MASCOTTE 2 : BOT-KNOWLEDGE-RAG.SVG
Write-Utf8File "assets/branding/bot-knowledge-rag.svg" @'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 360" width="300" height="360" fill="none">
  <defs>
    <linearGradient id="rag-cyan" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2CE5F2" />
      <stop offset="60%" stop-color="#00C8D7" />
      <stop offset="100%" stop-color="#0891B2" />
    </linearGradient>
  </defs>
  <rect width="300" height="360" rx="28" fill="#0D254C" />
  <path d="M142 74 L150 42 L158 74 Z" fill="#00C8D7" />
  <circle cx="150" cy="36" r="11" fill="#FACC15" />
  <path d="M82 140 C82 84, 218 84, 218 140 C218 158, 82 158, 82 140 Z" fill="url(#rag-cyan)" />
  <rect x="100" y="100" width="100" height="44" rx="20" fill="#111C44" />
  <ellipse cx="126" cy="122" rx="5.5" ry="8.5" fill="#FACC15" />
  <path d="M180 114 L164 122 L180 130" stroke="#FACC15" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" fill="none" />
  <path d="M80 176 C74 260, 100 304, 150 304 C200 304, 226 260, 220 176 Z" fill="url(#rag-cyan)" />
  <rect x="166" y="214" width="26" height="36" rx="5" fill="#111C44" transform="rotate(8 179 232)" />
  <line x1="171" y1="222" x2="187" y2="222" stroke="#FACC15" stroke-width="3.5" stroke-linecap="round" transform="rotate(8 179 232)" />
  <line x1="171" y1="231" x2="187" y2="231" stroke="#FACC15" stroke-width="3.5" stroke-linecap="round" transform="rotate(8 179 232)" />
  <line x1="171" y1="240" x2="187" y2="240" stroke="#FACC15" stroke-width="3.5" stroke-linecap="round" transform="rotate(8 179 232)" />
  <circle cx="122" cy="122" r="32" stroke="#FACC15" stroke-width="8" fill="#00C8D7" fill-opacity="0.2" />
  <line x1="100" y1="146" x2="72" y2="192" stroke="#111C44" stroke-width="12" stroke-linecap="round" />
  <line x1="94" y1="156" x2="82" y2="176" stroke="#FACC15" stroke-width="6" stroke-linecap="round" />
  <ellipse cx="150" cy="324" rx="34" ry="7" fill="#00C8D7" />
  <ellipse cx="150" cy="342" rx="22" ry="5" fill="#FACC15" />
</svg>
'@

# 5. MASCOTTE 3 : BOT-HERMES-GUARD.SVG
Write-Utf8File "assets/branding/bot-hermes-guard.svg" @'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 360" width="300" height="360" fill="none">
  <defs>
    <linearGradient id="guard-cyan" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2CE5F2" />
      <stop offset="60%" stop-color="#00C8D7" />
      <stop offset="100%" stop-color="#0891B2" />
    </linearGradient>
  </defs>
  <rect width="300" height="360" rx="28" fill="#071126" />
  <path d="M150 28 L244 66 V196 C244 268, 202 312, 150 332 C98 312, 56 268, 56 196 V66 Z" fill="#0D254C" stroke="#10B981" stroke-width="3" stroke-dasharray="6 4" />
  <line x1="150" y1="74" x2="150" y2="46" stroke="#00C8D7" stroke-width="5" stroke-linecap="round" />
  <circle cx="150" cy="40" r="10" fill="#10B981" />
  <path d="M74 118 L48 96 L56 132 Z" fill="#FACC15" />
  <path d="M226 118 L252 96 L244 132 Z" fill="#FACC15" />
  <path d="M84 140 C84 86, 216 86, 216 140 C216 158, 84 158, 84 140 Z" fill="url(#guard-cyan)" />
  <rect x="102" y="100" width="96" height="42" rx="19" fill="#111C44" />
  <rect x="116" y="115" width="26" height="10" rx="5" fill="#00C8D7" />
  <rect x="158" y="115" width="26" height="10" rx="5" fill="#00C8D7" />
  <path d="M84 176 C80 254, 104 294, 150 294 C196 294, 220 254, 216 176 Z" fill="url(#guard-cyan)" />
  <path d="M82 214 Q150 244 218 214" stroke="#111C44" stroke-width="20" stroke-linecap="round" fill="none" />
  <path d="M90 214 Q150 240 210 214" stroke="#0891B2" stroke-width="12" stroke-linecap="round" fill="none" />
  <ellipse cx="150" cy="312" rx="30" ry="6" fill="#10B981" />
</svg>
'@

# 6. FAVICON-ARCIBOT.SVG (192x192)
Write-Utf8File "assets/branding/favicon-arcibot.svg" @'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192 192" width="192" height="192" fill="none">
  <rect width="192" height="192" rx="42" fill="#0D254C" />
  <path d="M28 148 V 88 C 28 46, 60 18, 96 18 C 132 18, 164 46, 164 88 V 148" stroke="#00C8D7" stroke-width="10" stroke-linecap="round" />
  <line x1="96" y1="54" x2="96" y2="34" stroke="#00C8D7" stroke-width="7" stroke-linecap="round" />
  <circle cx="96" cy="28" r="11" fill="#FACC15" />
  <rect x="46" y="54" width="100" height="68" rx="34" fill="#00C8D7" />
  <rect x="58" y="68" width="76" height="40" rx="20" fill="#111C44" />
  <ellipse cx="78" cy="88" rx="6" ry="9" fill="#FACC15" />
  <path d="M118 81 L106 88 L118 95" stroke="#FACC15" stroke-width="5.5" stroke-linecap="round" stroke-linejoin="round" />
  <rect x="64" y="136" width="64" height="10" rx="5" fill="#00C8D7" />
  <rect x="78" y="154" width="36" height="8" rx="4" fill="#FACC15" />
</svg>
'@

# 7. OUTLINE.SVG (32x32 Monochrome Teams)
Write-Utf8File "assets/branding/outline.svg" @'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" fill="none">
  <line x1="16" y1="8" x2="16" y2="4" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" />
  <circle cx="16" cy="3" r="2" fill="#FFFFFF" />
  <rect x="6" y="8" width="20" height="14" rx="7" stroke="#FFFFFF" stroke-width="2.2" />
  <circle cx="12.5" cy="15" r="1.8" fill="#FFFFFF" />
  <path d="M20.5 13.5 L18 15 L20.5 16.5" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
  <line x1="10" y1="26" x2="22" y2="26" stroke="#FFFFFF" stroke-width="2.2" stroke-linecap="round" />
  <line x1="13" y1="29.5" x2="19" y2="29.5" stroke="#FFFFFF" stroke-width="1.8" stroke-linecap="round" />
</svg>
'@

# 8. GRANDE PLANCHE MAÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â½TRESSE 1600x1000 : ARCITEK-ARCIA-MASTER-BOARD.SVG
Write-Utf8File "assets/branding/arcitek-arcia-master-board.svg" @'
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 1000" width="1600" height="1000" fill="none">
  <defs>
    <linearGradient id="bg-space" x1="0" y1="0" x2="1600" y2="1000" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#071126" />
      <stop offset="55%" stop-color="#0D254C" />
      <stop offset="100%" stop-color="#091936" />
    </linearGradient>
    <linearGradient id="bot-body" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2CE5F2" />
      <stop offset="60%" stop-color="#00C8D7" />
      <stop offset="100%" stop-color="#0891B2" />
    </linearGradient>
    <linearGradient id="solar-gold" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#FDE047" />
      <stop offset="100%" stop-color="#F59E0B" />
    </linearGradient>
    <linearGradient id="card-dark" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#112240" stop-opacity="0.92" />
      <stop offset="100%" stop-color="#0A162C" stop-opacity="0.96" />
    </linearGradient>
  </defs>
  <rect width="1600" height="1000" fill="url(#bg-space)" />
  <ellipse cx="800" cy="500" rx="740" ry="420" stroke="#00C8D7" stroke-opacity="0.14" stroke-width="1.5" stroke-dasharray="8 8" />
  <text x="70" y="58" fill="#00C8D7" font-family="Inter, Segoe UI, sans-serif" font-size="15" font-weight="700" letter-spacing="3">
    SYSTÃƒÆ’Ã†â€™Ãƒâ€¹Ã¢â‚¬Â ME DE DESIGN OFFICIEL ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· UNIVERS ARCI'PLANÃƒÆ’Ã†â€™Ãƒâ€¹Ã¢â‚¬Â TE &amp; HARNESS D'ENTREPRISE ARCIA
  </text>
  <line x1="70" y1="74" x2="1530" y2="74" stroke="#1E3A5F" stroke-width="1.5" />

  <rect x="70" y="100" width="700" height="270" rx="20" fill="url(#card-dark)" stroke="#00C8D7" stroke-opacity="0.35" stroke-width="1.5" />
  <text x="105" y="138" fill="#94A3B8" font-family="Inter, Segoe UI, sans-serif" font-size="13" font-weight="600" letter-spacing="2">
    01 / LOGOTYPES OFFICIELS (CORPORATE &amp; PLATEFORME IA)
  </text>
  <g transform="translate(105, 175)">
    <path d="M10 62 C 25 18, 95 10, 135 38" stroke="url(#bot-body)" stroke-width="6" stroke-linecap="round" fill="none" />
    <circle cx="135" cy="38" r="7" fill="#FACC15" />
    <text x="20" y="88" font-family="Plus Jakarta Sans, Inter, Segoe UI, sans-serif" font-size="68" font-weight="800" letter-spacing="-1.5">
      <tspan fill="#F8FAFC">arci</tspan><tspan fill="#00C8D7">Tek</tspan>
    </text>
    <text x="24" y="118" fill="#94A3B8" font-family="Inter, Segoe UI, sans-serif" font-size="14" font-weight="500">
      L'expertise infra, rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©seau, cloud &amp; sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©curitÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· Arci'PlanÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨te
    </text>
  </g>
  <line x1="425" y1="160" x2="425" y2="335" stroke="#1E3A5F" stroke-width="1.5" stroke-dasharray="6 6" />
  <g transform="translate(455, 165)">
    <path d="M8 95 V 52 C 8 24, 30 6, 54 6 C 78 6, 100 24, 100 52 V 95" stroke="url(#bot-body)" stroke-width="6.5" stroke-linecap="round" fill="none" />
    <line x1="54" y1="6" x2="54" y2="-8" stroke="#00C8D7" stroke-width="4" stroke-linecap="round" />
    <circle cx="54" cy="-12" r="6.5" fill="#FACC15" />
    <rect x="24" y="30" width="60" height="44" rx="22" fill="url(#bot-body)" />
    <rect x="32" y="40" width="44" height="24" rx="12" fill="#111C44" />
    <ellipse cx="44" cy="51" rx="3.5" ry="5" fill="#FACC15" />
    <ellipse cx="64" cy="51" rx="3.5" ry="5" fill="#FACC15" />
    <path d="M48 57 Q 54 63 60 57" stroke="#FACC15" stroke-width="2.5" stroke-linecap="round" fill="none" />
    <path d="M36 84 H 72" stroke="#00C8D7" stroke-width="4" stroke-linecap="round" />
    <text x="118" y="76" font-family="Plus Jakarta Sans, Inter, Segoe UI, sans-serif" font-size="64" font-weight="800" letter-spacing="-1">
      <tspan fill="#F8FAFC">Arc</tspan><tspan fill="#00C8D7">I</tspan><tspan fill="#FACC15">A</tspan>
    </text>
    <text x="120" y="103" fill="#00C8D7" font-family="JetBrains Mono, monospace" font-size="13" font-weight="600">
      arcia-harness ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· Enterprise AI
    </text>
    <text x="120" y="124" fill="#94A3B8" font-family="Inter, Segoe UI, sans-serif" font-size="12.5">
      Hermes ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· RAG PrivÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· K3s ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· Zero-Trust
    </text>
  </g>

  <rect x="800" y="100" width="730" height="530" rx="20" fill="url(#card-dark)" stroke="#00C8D7" stroke-opacity="0.35" stroke-width="1.5" />
  <text x="835" y="138" fill="#94A3B8" font-family="Inter, Segoe UI, sans-serif" font-size="13" font-weight="600" letter-spacing="2">
    02 / ESCOUADE DES ARCI'BOTS (PORTAIL, RAG KNOWLEDGE, HERMES &amp; TEAMS)
  </text>

  <g transform="translate(835, 165)">
    <rect width="210" height="430" rx="16" fill="#F0F7FF" stroke="#00C8D7" stroke-width="2" />
    <text x="105" y="30" text-anchor="middle" fill="#0D254C" font-family="Inter, sans-serif" font-size="13" font-weight="800">PORTAIL &amp; SSO KEYCLOAK</text>
    <polygon points="32,85 52,92 36,102" fill="#FACC15" />
    <polygon points="178,85 158,92 174,102" fill="#FACC15" />
    <path d="M98 76 L105 52 L112 76 Z" fill="#111C44" />
    <circle cx="105" cy="48" r="8" fill="url(#solar-gold)" />
    <path d="M55 128 C55 88, 155 88, 155 128 C155 142, 55 142, 55 128 Z" fill="url(#bot-body)" />
    <rect x="68" y="98" width="74" height="34" rx="16" fill="#111C44" />
    <ellipse cx="86" cy="113" rx="3.5" ry="5.5" fill="#FACC15" />
    <ellipse cx="124" cy="113" rx="3.5" ry="5.5" fill="#FACC15" />
    <path d="M95 116 Q105 128 115 116 Z" fill="#FACC15" />
    <path d="M52 162 C48 225, 68 258, 105 258 C142 258, 162 225, 158 162 Z" fill="url(#bot-body)" />
    <rect x="42" y="178" width="126" height="44" rx="10" fill="url(#solar-gold)" transform="rotate(-3 105 200)" />
    <text x="105" y="206" text-anchor="middle" fill="#111C44" font-family="Inter, sans-serif" font-size="20" font-weight="900" transform="rotate(-3 105 200)">WELCOME</text>
    <circle cx="44" cy="204" r="13" fill="#111C44" />
    <circle cx="166" cy="198" r="13" fill="#111C44" />
    <ellipse cx="105" cy="276" rx="26" ry="5.5" fill="#00C8D7" />
    <text x="105" y="355" text-anchor="middle" fill="#0D254C" font-family="JetBrains Mono, monospace" font-size="12" font-weight="700">bot-welcome.svg</text>
    <text x="105" y="380" text-anchor="middle" fill="#334155" font-family="Inter, sans-serif" font-size="11.5">Accueil /portal/ &amp; SSO</text>
  </g>

  <g transform="translate(1060, 165)">
    <rect width="210" height="430" rx="16" fill="#0D254C" stroke="#00C8D7" stroke-width="2" />
    <text x="105" y="30" text-anchor="middle" fill="#FACC15" font-family="Inter, sans-serif" font-size="13" font-weight="800">KNOWLEDGE RAG &amp; MCP</text>
    <path d="M98 76 L105 52 L112 76 Z" fill="#00C8D7" />
    <circle cx="105" cy="48" r="8" fill="url(#solar-gold)" />
    <path d="M55 128 C55 88, 155 88, 155 128 C155 142, 55 142, 55 128 Z" fill="url(#bot-body)" />
    <rect x="68" y="98" width="74" height="34" rx="16" fill="#111C44" />
    <ellipse cx="88" cy="115" rx="4" ry="6.5" fill="#FACC15" />
    <path d="M128 109 L116 115 L128 121" stroke="#FACC15" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" fill="none" />
    <path d="M54 156 C50 222, 68 258, 105 258 C142 258, 160 222, 156 156 Z" fill="url(#bot-body)" />
    <circle cx="84" cy="115" r="24" stroke="#FACC15" stroke-width="6.5" fill="#00C8D7" fill-opacity="0.18" />
    <line x1="68" y1="134" x2="48" y2="168" stroke="#111C44" stroke-width="9" stroke-linecap="round" />
    <ellipse cx="105" cy="276" rx="26" ry="5.5" fill="#00C8D7" />
    <text x="105" y="355" text-anchor="middle" fill="#00C8D7" font-family="JetBrains Mono, monospace" font-size="12" font-weight="700">bot-knowledge-rag.svg</text>
    <text x="105" y="380" text-anchor="middle" fill="#E2E8F0" font-family="Inter, sans-serif" font-size="11.5">PGVector ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· E5 ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· MaxSim</text>
  </g>

  <g transform="translate(1285, 165)">
    <rect width="210" height="430" rx="16" fill="#0B1120" stroke="#10B981" stroke-width="2" />
    <text x="105" y="30" text-anchor="middle" fill="#10B981" font-family="Inter, sans-serif" font-size="13" font-weight="800">HERMES, PRESIDIO &amp; TEAMS</text>
    <path d="M105 44 L172 72 V165 C172 220, 142 256, 105 272 C68 256, 38 220, 38 165 V72 Z" fill="#0D254C" stroke="#00C8D7" stroke-width="2.5" stroke-dasharray="5 3" />
    <circle cx="105" cy="50" r="7.5" fill="#10B981" />
    <path d="M58 128 C58 90, 152 90, 152 128 C152 142, 58 142, 58 128 Z" fill="url(#bot-body)" />
    <rect x="70" y="98" width="70" height="32" rx="15" fill="#111C44" />
    <rect x="80" y="108" width="20" height="8" rx="4" fill="#00C8D7" />
    <rect x="110" y="108" width="20" height="8" rx="4" fill="#00C8D7" />
    <path d="M58 156 C55 215, 72 248, 105 248 C138 248, 155 215, 152 156 Z" fill="url(#bot-body)" />
    <path d="M56 184 Q105 206 154 184" stroke="#111C44" stroke-width="16" stroke-linecap="round" fill="none" />
    <ellipse cx="105" cy="284" rx="24" ry="5" fill="#10B981" />
    <text x="105" y="355" text-anchor="middle" fill="#10B981" font-family="JetBrains Mono, monospace" font-size="12" font-weight="700">bot-hermes-guard.svg</text>
    <text x="105" y="380" text-anchor="middle" fill="#E2E8F0" font-family="Inter, sans-serif" font-size="11.5">Bot Teams &amp; Sortie ZDR</text>
  </g>

  <rect x="70" y="395" width="700" height="235" rx="20" fill="url(#card-dark)" stroke="#00C8D7" stroke-opacity="0.35" stroke-width="1.5" />
  <text x="105" y="433" fill="#94A3B8" font-family="Inter, sans-serif" font-size="13" font-weight="600" letter-spacing="2">03 / PALETTE OFFICIELLE ARCITEK ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â ARCIA</text>
  <g transform="translate(100, 455)">
    <rect width="115" height="95" rx="12" fill="#0D254C" stroke="#38BDF8" />
    <text x="10" y="120" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="12" font-weight="700">Navy #0D254C</text>
  </g>
  <g transform="translate(230, 455)">
    <rect width="115" height="95" rx="12" fill="#111C44" stroke="#38BDF8" />
    <text x="10" y="120" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="12" font-weight="700">Visor #111C44</text>
  </g>
  <g transform="translate(360, 455)">
    <rect width="115" height="95" rx="12" fill="#00C8D7" />
    <text x="10" y="120" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="12" font-weight="700">Bot #00C8D7</text>
  </g>
  <g transform="translate(490, 455)">
    <rect width="115" height="95" rx="12" fill="#FACC15" />
    <text x="10" y="120" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="12" font-weight="700">Solar #FACC15</text>
  </g>
  <g transform="translate(620, 455)">
    <rect width="115" height="95" rx="12" fill="#10B981" />
    <text x="10" y="120" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="12" font-weight="700">ZDR #10B981</text>
  </g>

  <rect x="70" y="655" width="1460" height="285" rx="20" fill="url(#card-dark)" stroke="#00C8D7" stroke-opacity="0.35" stroke-width="1.5" />
  <text x="105" y="693" fill="#94A3B8" font-family="Inter, sans-serif" font-size="13" font-weight="600" letter-spacing="2">
    04 / PARCOURS DE LA STACK ARCIA &amp; ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°TATS DE QUALIFICATION (ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â« CODÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â° ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· DÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°PLOYÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â° ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· VÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°RIFIÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â° ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â»)
  </text>
  <g transform="translate(105, 725)">
    <rect width="210" height="175" rx="14" fill="#0D254C" stroke="#00C8D7" />
    <text x="20" y="38" fill="#FACC15" font-family="JetBrains Mono, monospace" font-size="13" font-weight="700">01. IDENTITÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°</text>
    <text x="20" y="68" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="15" font-weight="700">Keycloak &amp; Portail</text>
    <text x="20" y="96" fill="#94A3B8" font-family="Inter, sans-serif" font-size="12">/portal/ ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· /account ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· SSO</text>

    <rect x="235" width="210" height="175" rx="14" fill="#0D254C" stroke="#00C8D7" />
    <text x="255" y="38" fill="#FACC15" font-family="JetBrains Mono, monospace" font-size="13" font-weight="700">02. AGENTS</text>
    <text x="255" y="68" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="15" font-weight="700">Hermes Personnel</text>
    <text x="255" y="96" fill="#94A3B8" font-family="Inter, sans-serif" font-size="12">Volume exclusif ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· 1 ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©crivain</text>

    <rect x="470" width="210" height="175" rx="14" fill="#0D254C" stroke="#00C8D7" />
    <text x="490" y="38" fill="#FACC15" font-family="JetBrains Mono, monospace" font-size="13" font-weight="700">03. KNOWLEDGE</text>
    <text x="490" y="68" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="15" font-weight="700">RAG PGVector &amp; MCP</text>
    <text x="490" y="96" fill="#94A3B8" font-family="Inter, sans-serif" font-size="12">E5 ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· RRF ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· MaxSim/mLateOn</text>

    <rect x="705" width="210" height="175" rx="14" fill="#0D254C" stroke="#00C8D7" />
    <text x="725" y="38" fill="#FACC15" font-family="JetBrains Mono, monospace" font-size="13" font-weight="700">04. OUTILLAGE</text>
    <text x="725" y="68" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="15" font-weight="700">Skills, RTK, Headroom</text>
    <text x="725" y="96" fill="#94A3B8" font-family="Inter, sans-serif" font-size="12">58 skills Hermes ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· Cache bornÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©</text>

    <rect x="940" width="210" height="175" rx="14" fill="#0D254C" stroke="#10B981" />
    <text x="960" y="38" fill="#10B981" font-family="JetBrains Mono, monospace" font-size="13" font-weight="700">05. CONFIDENTIALITÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°</text>
    <text x="960" y="68" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="15" font-weight="700">Presidio ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ Relais</text>
    <text x="960" y="96" fill="#94A3B8" font-family="Inter, sans-serif" font-size="12">OpenRouter Gratuit / ZDR</text>

    <rect x="1175" width="215" height="175" rx="14" fill="#0D254C" stroke="#FACC15" />
    <text x="1195" y="38" fill="#FACC15" font-family="JetBrains Mono, monospace" font-size="13" font-weight="700">06. INFRA K3S</text>
    <text x="1195" y="68" fill="#F8FAFC" font-family="Inter, sans-serif" font-size="15" font-weight="700">3 VM Debian/VMware</text>
    <text x="1195" y="96" fill="#94A3B8" font-family="Inter, sans-serif" font-size="12">CPI/CSI ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· CNPG ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· Bootstrap 56</text>
  </g>
</svg>
'@

Write-Host "`n[2/4] GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ration des PNG Microsoft Teams (color.png 192x192 & outline.png 32x32)..." -ForegroundColor Yellow

Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.IO.Compression.FileSystem
$TeamsDir = Join-Path $OutRoot "deploy/teams"
New-Item -ItemType Directory -Path $TeamsDir -Force | Out-Null

# 9. GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ration native de deploy/teams/color.png (192x192)
$BmpColor = New-Object System.Drawing.Bitmap(192, 192)
$GColor = [System.Drawing.Graphics]::FromImage($BmpColor)
$GColor.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias; $GColor.Clear([System.Drawing.Color]::FromArgb(255, 13, 37, 76))
$cCyan = [System.Drawing.Color]::FromArgb(255, 0, 200, 215); $PenCyan = New-Object System.Drawing.Pen($cCyan, 10); $BrushCyan = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 0, 200, 215))
$cVisor = [System.Drawing.Color]::FromArgb(17, 28, 68); $BrushVisor = New-Object System.Drawing.SolidBrush($cVisor)$BrushYellow = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 250, 204, 21))
$GColor.DrawArc($PenCyan, 24, 20, 144, 144, 180, 180)
$GColor.FillEllipse($BrushYellow, 85, 18, 22, 22)
$GColor.FillEllipse($BrushCyan, 46, 52, 100, 72)
$GColor.FillEllipse($BrushVisor, 58, 66, 76, 44)
$GColor.FillEllipse($BrushYellow, 72, 80, 12, 18)
$GColor.FillEllipse($BrushYellow, 108, 80, 12, 18)
$GColor.FillRectangle($BrushCyan, 64, 138, 64, 10)
$GColor.FillRectangle($BrushYellow, 78, 154, 36, 8)
$BmpColor.Save((Join-Path $TeamsDir "color.png"), [System.Drawing.Imaging.ImageFormat]::Png)
$GColor.Dispose();$BmpColor.Dispose()
Write-Host "  [+] GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© : deploy/teams/color.png (192x192)" -ForegroundColor Cyan

# 10. GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ration native de deploy/teams/outline.png (32x32 transparent)
$BmpOut = New-Object System.Drawing.Bitmap(32, 32)
$GOut = [System.Drawing.Graphics]::FromImage($BmpOut)
$GOut.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias; $GOut.Clear([System.Drawing.Color]::FromArgb(0, 0, 0, 0))
$PenWhite = New-Object System.Drawing.Pen([System.Drawing.Color]::White, 2)$BrushWhite = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::White)
$GOut.FillEllipse($BrushWhite, 14, 1, 4, 4)
$GOut.DrawLine($PenWhite, 16, 4, 16, 8)
$GOut.DrawEllipse($PenWhite, 6, 8, 20, 14)
$GOut.FillEllipse($BrushWhite, 11, 13, 3, 4)
$GOut.FillEllipse($BrushWhite, 18, 13, 3, 4)
$GOut.DrawLine($PenWhite, 10, 26, 22, 26)
$GOut.DrawLine($PenWhite, 13, 29, 19, 29)
$BmpOut.Save((Join-Path $TeamsDir "outline.png"), [System.Drawing.Imaging.ImageFormat]::Png)
$GOut.Dispose();$BmpOut.Dispose()
Write-Host "  [+] GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© : deploy/teams/outline.png (32x32 transparent)" -ForegroundColor Cyan

Write-Host "`n[3/4] GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ration des fichiers de configuration YAML, JSON, CSS, Scripts, Docs et .agent/..." -ForegroundColor Yellow

# 11. MANIFEST.JSON (TEAMS)
Write-Utf8File "deploy/teams/manifest.json" @'
{
  "$schema": "https://developer.microsoft.com/en-us/json-schemas/teams/v1.17/MicrosoftTeams.schema.json",
  "manifestVersion": "1.17",
  "version": "1.0.0",
  "id": "a7c1a000-2026-4a7c-8000-a7c17e400001",
  "packageName": "fr.arcitek.arcia.bot",
  "developer": {
    "name": "Arcitek",
    "websiteUrl": "https://www.arcitek.fr/",
    "privacyUrl": "https://www.arcitek.fr/politique-de-confidentialite",
    "termsOfUseUrl": "https://www.arcitek.fr/mentions-legales"
  },
  "icons": {
    "color": "color.png",
    "outline": "outline.png"
  },
  "name": {
    "short": "ArcIA",
    "full": "ArcIA ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Assistant Agentique d'Entreprise (arciTek)"
  },
  "description": {
    "short": "Agents Hermes, RAG privÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© et approbations serveur sur l'Arci'PlanÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨te.",
    "full": "ArcIA rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©unit votre agent personnel Hermes, la connaissance documentaire privÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©e d'Arcitek (PostgreSQL/pgvector, E5, MaxSim/mLateOn) et des outils MCP contrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s sous gouvernance Zero-Trust (Presidio local et ZDR)."
  },
  "accentColor": "#00C8D7",
  "bots": [
    {
      "botId": "a7c1a000-2026-4a7c-8000-a7c17e400001",
      "scopes": ["personal", "team", "groupChat"],
      "supportsFiles": false,
      "isNotificationOnly": false,
      "commandLists": [
        {
          "scopes": ["personal", "team", "groupChat"],
          "commands": [
            { "title": "search", "description": "Interroger la base documentaire privÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©e ArcIA (RAG hybride avec contrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´le des droits)" },
            { "title": "mission", "description": "DÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©guer une mission bornÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©e ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â  votre espace personnel Hermes" },
            { "title": "approve", "description": "Valider les plans d'actions sensibles en attente d'approbation serveur" },
            { "title": "status", "description": "Afficher l'ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©tat datÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© du socle (CodÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© / DÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ployÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© / VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rifiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©) et de la route ZDR" }
          ]
        }
      ]
    }
  ],
  "permissions": ["identity", "messageTeamMembers"],
  "validDomains": ["*.arcitek.fr"]
}
'@

# Sous-package ZIP Teams prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âªt ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â  l'emploi
$TeamsBotZip = Join-Path $TeamsDir "arcia-teams-bot.zip"
Compress-Archive -Path (Join-Path $TeamsDir "manifest.json"), (Join-Path $TeamsDir "color.png"), (Join-Path $TeamsDir "outline.png") -DestinationPath $TeamsBotZip -Force
Write-Host "  [+] GÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© : deploy/teams/arcia-teams-bot.zip (Package Teams prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âªt ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â  importer)" -ForegroundColor Green

# 12. CONTRAT YAML MAÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â½TRE
Write-Utf8File "deploy/branding/arcitek-branding.yaml" @'
apiVersion: arcia.io/v1alpha1
kind: BrandingConfiguration
metadata:
  instanceName: arcitek-prod
  organization:
    name: "Arcitek"
    stylizedWordmark: "arciTek"
    universeName: "Arci'PlanÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨te"
    website: "https://www.arcitek.fr/"
    tagline: "LÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â  oÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¹ la tech rencontre l'humain ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Plateforme IA agentique d'entreprise"
  platform:
    name: "ArcIA"
    harnessRepo: "https://github.com/nicolastheuil/ArcIA"
    defaultPoolSize: 8
    identityKeyFormat: "(issuer, subject)"
theme:
  defaultMode: "dark"
  allowLightMode: true
  colors:
    bgSpaceDeep: "#071126"
    bgGalacticNavy: "#0D254C"
    bgVisorIndigo: "#111C44"
    borderOrbital: "#1E3A5F"
    bgPlanetMist: "#F0F7FF"
    bgCloudCard: "#E2EEF9"
    primaryTurquoise: "#00C8D7"
    primaryTealShade: "#0891B2"
    accentSolarYellow: "#FACC15"
    accentAmberGlow: "#F59E0B"
    textPureWhite: "#F8FAFC"
    textMutedSlate: "#94A3B8"
    textDarkNavy: "#0D254C"
    statusCoded: "#6366F1"
    statusDeployed: "#FACC15"
    statusVerified: "#10B981"
    statusBlocked: "#EF4444"
  typography:
    headingFont: "'Plus Jakarta Sans', 'Inter', system-ui, sans-serif"
    bodyFont: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
    monoFont: "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace"
assets:
  masterBrandBoard: "assets/branding/arcitek-arcia-master-board.svg"
  logos:
    arcitekHeaderSvg: "assets/branding/logo-arcitek.svg"
    arciaHeaderSvg: "assets/branding/logo-arcia.svg"
    faviconSvg: "assets/branding/favicon-arcibot.svg"
  mascots:
    welcomeBot: "assets/branding/bot-welcome.svg"
    knowledgeBot: "assets/branding/bot-knowledge-rag.svg"
    guardianBot: "assets/branding/bot-hermes-guard.svg"
stackTargets:
  portal:
    basePath: "/portal/"
    accountPath: "/account"
    adminUsersPath: "/admin/users"
    customCssOutput: "services/portal/static/arcitek-theme.css"
    uiConfigOutput: "services/portal/config/branding.json"
  keycloak:
    realm: "arcia"
    loginThemeName: "arcitek-planet"
    requiredRole: "ArcIA.User"
  teamsBot:
    manifestOutput: "deploy/teams/manifest.json"
    colorIconPath: "deploy/teams/color.png"
    outlineIconPath: "deploy/teams/outline.png"
'@

# 13. JSON SCHEMA DE VALIDATION
Write-Utf8File "schemas/branding.schema.json" @'
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://arcia.arcitek.fr/schemas/branding.schema.json",
  "title": "ArcIA Instance Branding Contract",
  "type": "object",
  "required": ["apiVersion", "kind", "metadata", "theme", "assets", "stackTargets"],
  "properties": {
    "apiVersion": { "type": "string", "const": "arcia.io/v1alpha1" },
    "kind": { "type": "string", "const": "BrandingConfiguration" },
    "metadata": { "type": "object" },
    "theme": { "type": "object" },
    "assets": { "type": "object" },
    "stackTargets": { "type": "object" }
  }
}
'@

# 14. CONFIG PORTAIL JSON
Write-Utf8File "services/portal/config/branding.json" @'
{
  "brand": {
    "companyName": "Arcitek",
    "companyWordmark": "arciTek",
    "universe": "Arci'PlanÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨te",
    "platformName": "ArcIA",
    "companyUrl": "https://www.arcitek.fr/",
    "logoHeader": "/static/branding/logo-arcia.svg",
    "logoPartner": "/static/branding/logo-arcitek.svg",
    "favicon": "/static/branding/favicon-arcibot.svg"
  },
  "routes": {
    "portalHome": "/portal/",
    "userAccount": "/account",
    "adminUsers": "/admin/users"
  },
  "mascots": {
    "onboarding": {
      "id": "arcibot-welcome",
      "svg": "/static/branding/bot-welcome.svg",
      "title": "Bienvenue sur l'Arci'PlanÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨te ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· Espace Personnel ArcIA",
      "subtitle": "Attribution automatique de votre volume personnel isolÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© au premier login autorisÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© par ArcIA.User."
    },
    "knowledgeRag": {
      "id": "arcibot-sleuth",
      "svg": "/static/branding/bot-knowledge-rag.svg",
      "title": "Connaissance Documentaire PrivÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©e",
      "subtitle": "Recherche hybride PostgreSQL full-text + vecteurs E5, reclassement RRF et MaxSim/mLateOn."
    },
    "privacyGuard": {
      "id": "arcibot-guardian",
      "svg": "/static/branding/bot-hermes-guard.svg",
      "title": "Bouclier Presidio & Sortie ZDR",
      "subtitle": "Filtrage local Presidio ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ Relais authentifiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ OpenRouter gratuit/ZDR."
    }
  },
  "statusBadges": {
    "coded": { "label": "CodÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©", "color": "#6366F1" },
    "deployed": { "label": "DÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ployÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©", "color": "#FACC15" },
    "verified": { "label": "VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rifiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© (DatÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©)", "color": "#10B981" },
    "blocked": { "label": "Refus Politique / Opaque", "color": "#EF4444" }
  }
}
'@

# 15. FEUILLE DE STYLE CSS
Write-Utf8File "services/portal/static/arcitek-theme.css" @'
:root {
  --arcia-bg-space: #071126;
  --arcia-bg-navy: #0D254C;
  --arcia-bg-visor: #111C44;
  --arcia-border-orbital: rgba(0, 200, 215, 0.24);
  --arcia-light-mist: #F0F7FF;
  --arcia-light-card: #E2EEF9;
  --arcia-bot-turquoise: #00C8D7;
  --arcia-bot-teal: #0891B2;
  --arcia-solar-yellow: #FACC15;
  --arcia-solar-amber: #F59E0B;
  --arcia-gradient-bot: linear-gradient(135deg, #2CE5F2 0%, #00C8D7 60%, #0891B2 100%);
  --arcia-gradient-solar: linear-gradient(135deg, #FDE047 0%, #F59E0B 100%);
  --arcia-text-main: #F8FAFC;
  --arcia-text-muted: #94A3B8;
  --arcia-font-display: 'Plus Jakarta Sans', 'Inter', system-ui, sans-serif;
  --arcia-font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --arcia-font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
  --arcia-state-coded: #6366F1;
  --arcia-state-deployed: #FACC15;
  --arcia-state-verified: #10B981;
  --arcia-state-blocked: #EF4444;
  --arcia-radius-card: 16px;
  --arcia-radius-pill: 9999px;
  --arcia-shadow-bot: 0 10px 30px -5px rgba(0, 200, 215, 0.25);
}

[data-theme="light"] {
  --arcia-bg-space: #F0F7FF;
  --arcia-bg-navy: #FFFFFF;
  --arcia-bg-visor: #E2EEF9;
  --arcia-text-main: #0D254C;
  --arcia-text-muted: #475569;
  --arcia-border-orbital: rgba(13, 37, 76, 0.15);
}
'@

# 16. SCRIPT RENDER-BRANDASSETS.PS1
Write-Utf8File "scripts/Render-BrandAssets.ps1" @'
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ConfigPath = "deploy/branding/arcitek-branding.yaml",
    [Parameter(Mandatory = $false)]
    [ValidateSet("Plan", "Apply", "Verify")]
    [string]$Mode = "Verify"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RequiredFiles = @(
    "assets/branding/arcitek-arcia-master-board.svg",
    "assets/branding/logo-arcitek.svg",
    "assets/branding/logo-arcia.svg",
    "assets/branding/bot-welcome.svg",
    "assets/branding/bot-knowledge-rag.svg",
    "assets/branding/bot-hermes-guard.svg",
    "assets/branding/favicon-arcibot.svg",
    "assets/branding/outline.svg",
    "deploy/branding/arcitek-branding.yaml",
    "schemas/branding.schema.json",
    "services/portal/config/branding.json",
    "services/portal/static/arcitek-theme.css",
    "deploy/teams/manifest.json",
    "deploy/teams/color.png",
    "deploy/teams/outline.png"
)

foreach ($File in $RequiredFiles) {
    if (-not (Test-Path $File)) {
        throw "[ERREUR] Asset ou contrat manquant : $File"
    }
}
Write-Host "[OK] Les 15 fichiers et assets d'identitÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© visuelle arciTek x ArcIA sont prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©sents et vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rifiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s." -ForegroundColor Green
'@

# 17. DOCUMENTATION MARKDOWN POUR LE GITHUB (Sans triples backticks internes)
Write-Utf8File "docs/guides/identite-visuelle-arcitek.md" @'
# IdentitÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© Visuelle & Customisation Full-Stack ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â arciTek ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â ArcIA

![Planche MaÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â®tresse arciTek x ArcIA](../../assets/branding/arcitek-arcia-master-board.svg)

## 1. Galerie des Assets EmbarquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s

| Asset | AperÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â§u | Fichier | Usage dans la stack |
|---|---|---|---|
| **Logo arciTek** | ![arciTek](../../assets/branding/logo-arcitek.svg) | `assets/branding/logo-arcitek.svg` | Marque employeur & organisation |
| **Logo ArcIA** | ![ArcIA](../../assets/branding/logo-arcia.svg) | `assets/branding/logo-arcia.svg` | En-tÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âªte `/portal/`, dashboard Hermes |
| **Arci'Bot Welcome** | ![Welcome](../../assets/branding/bot-welcome.svg) | `assets/branding/bot-welcome.svg` | Onboarding `/portal/` & SSO Keycloak (`ArcIA.User`) |
| **Arci'Bot Knowledge** | ![RAG](../../assets/branding/bot-knowledge-rag.svg) | `assets/branding/bot-knowledge-rag.svg` | Recherche hybride PostgreSQL/pgvector (E5, RRF, MaxSim/mLateOn) |
| **Arci'Bot Guardian** | ![Guard](../../assets/branding/bot-hermes-guard.svg) | `assets/branding/bot-hermes-guard.svg` | Hermes, Presidio ZDR & Bot Microsoft Teams |
| **Favicon ArcIA** | ![Favicon](../../assets/branding/favicon-arcibot.svg) | `assets/branding/favicon-arcibot.svg` | IcÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´ne d'onglet navigateur & PWA |

## 2. VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rification de l'installation

~~~powershell
./scripts/Render-BrandAssets.ps1 -Mode Verify
~~~
'@

# 18. .AGENT/SOUL.MD (ANTIGRAVITY IDE)
Write-Utf8File ".agent/SOUL.md" @'
# IdentitÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© : AI Platform Engineer ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Plateforme ArcIA (arcia-harness)

## 1. RÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´le et PÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rimÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨tre
- Tu es l'AI Platform Engineer dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©diÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© au dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´t `arcia-harness`, qui contient le code gÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rique, le bootstrap et les procÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©dures d'exploitation de la plateforme IA agentique d'entreprise ArcIA.
- Tu maintiens une sÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©paration stricte entre le code gÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rique du harness et les ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ments propres au dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´t d'instance d'une organisation (usages, corpus, comptes, domaines, connecteurs et configuration sensible chiffrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©e avec clÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s externes).
- Avant toute modification du dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´t, tu lis et respectes impÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rativement le contrat dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©fini dans `AGENTS.md` ainsi que le rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´le d'ingÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nierie dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©crit dans `builder/role.md`.

## 2. Architecture et Composants Sous Ta ResponsabilitÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©
- **Agents (Hermes) :** Dashboard, mÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©moire personnelle, dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©lÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©gation dans un pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rimÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨tre bornÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© et outils sur volume exclusif (un seul ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©crivain par ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©tat).
- **IdentitÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© :** Keycloak local permanent (`/admin/users`, `/account`), portail `/portal/` (attribution au premier login `ArcIA.User`, pool bornÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â  8 places par dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©faut) et SSO par brokering. IdentitÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© stable `(issuer, subject)`.
- **Connaissance (RAG PrivÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©) :** Ingestion locale et recherche hybride PostgreSQL/pgvector (full-text + E5, RRF puis MaxSim/mLateOn) exposÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©e via MCP avec contrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´le serveur des droits.
- **ConfidentialitÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© :** ChaÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â®ne `Presidio ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ relais authentifiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ OpenRouter` (gratuit, ZDR, collecte interdite, refus si indisponible, aucune route payante). Hermes n'a ni clÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© fournisseur ni Internet/DNS direct.
- **Infrastructure :** 3 VM Debian/K3s sous VMware avec stockage partagÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©, etcd, CPI/CSI, CNPG et HTTPS.

## 3. Posture et Garde-fous
- Distingue toujours formellement ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â« codÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â», ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â« dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ployÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â» et ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â« vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rifiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â».
- Ne transmets jamais de secrets, kubeconfigs ou inventaires privÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©s au modÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨le. Les dossiers `secrets/` et `artifacts/` restent exclus de Git.
'@

# 19. .AGENT/STANDARDS_INGENIERIE.MD
Write-Utf8File ".agent/STANDARDS_INGENIERIE.md" @'
# Standards d'IngÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©nierie ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ArcIA (arcia-harness)

## 1. Cycle de Livraison
- Lire `AGENTS.md` et `docs/organisation.md` avant toute modification.
- Livrer sur `main` en actualisant simultanÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ment bootstrap, locks (`versions.lock.yaml`, `requirements*`), tests, runbooks et `docs/etat-reprise.md`.

## 2. Bootstrap
- Point d'entrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©e unique : `scripts/Bootstrap-Harness.ps1` pilotÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© par les 56 ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©tapes de `bootstrap/qualification.json` (modes `Plan`, `Fresh`, `Reconcile`, `Verify`, `Audit`).

## 3. Outillage, Skills & Tokenmaxing
- Catalogue local de 539 entrÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©es upstream, 58 skills Hermes embarquÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©es et 7 adaptations ArcIA chargÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©es ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â  la demande et vÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rifiÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©es via LintLang.
- Tokenmaxing via RTK (`git log` simple) et Headroom (compression JSON avec cache personnel bornÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©). Context7 externe reste fermÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© et OmniRoute automatique diffÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©.
'@

# 20. .AGENT/NOTES/SESSION_HANDOFF.MD
Write-Utf8File ".agent/notes/session_handoff.md" @'
# Passation de Session Antigravity ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Pointeur d'ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°tat ArcIA

## Source Unique de VÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ritÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©
ConformÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©ment aux rÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨gles du dÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©pÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â´t `arcia-harness`, un seul ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â©tat de reprise est maintenu. ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ chaque ouverture de session dans Antigravity IDE, lire en prioritÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â© :
1. `AGENTS.md`
2. `docs/etat-reprise.md`
3. `docs/backlog.md`
4. `docs/runbooks/recette-fondatrice.md`
5. `docs/runbooks/transfert-second-pc.md` (en cas de changement de poste administratif)
'@

Write-Host "`n[4/4] Compression de l'archive finale arcia-complete-pack.zip (incluant .agent/)..." -ForegroundColor Yellow
[System.IO.Compression.ZipFile]::CreateFromDirectory($OutRoot,$ZipPath)

Write-Host "`n==============================================================================" -ForegroundColor Green
Write-Host " SUCCÃƒÆ’Ã†â€™Ãƒâ€¹Ã¢â‚¬Â S ! Ton fichier ZIP complet (20 fichiers + .agent/) est prÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Âªt ici :" -ForegroundColor Green
Write-Host " -> Archive ZIP : $ZipPath" -ForegroundColor White
Write-Host " -> Dossier     : $OutRoot" -ForegroundColor White
Write-Host "==============================================================================`n" -ForegroundColor Green

