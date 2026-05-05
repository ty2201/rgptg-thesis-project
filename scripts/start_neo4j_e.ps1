$ErrorActionPreference = "Continue"

$Neo4jHome = "E:\neo4j-codex\neo4j-5.26.25"
$JdkHome = "E:\neo4j-codex\jdk-21"
$LogPath = "E:\neo4j-codex\start-rgptg.log"
$Password = $env:NEO4J_PASSWORD

if (-not $Password) {
    throw "Set NEO4J_PASSWORD before running this script."
}

"==== rgptg neo4j start $(Get-Date -Format o) ====" | Set-Content -LiteralPath $LogPath -Encoding UTF8
"Neo4jHome=$Neo4jHome" | Add-Content -LiteralPath $LogPath -Encoding UTF8
"JdkHome=$JdkHome" | Add-Content -LiteralPath $LogPath -Encoding UTF8

try {
    $ConfPath = Join-Path $Neo4jHome "conf\neo4j.conf"
    $ConfText = Get-Content -LiteralPath $ConfPath -Raw
    if ($ConfText -notlike "*# rgptg local config*") {
        @"

# rgptg local config
server.default_listen_address=127.0.0.1
server.default_advertised_address=127.0.0.1
server.http.listen_address=127.0.0.1:7474
server.bolt.listen_address=127.0.0.1:7687
dbms.security.auth_enabled=true
"@ | Add-Content -LiteralPath $ConfPath -Encoding UTF8
        "Appended rgptg config." | Add-Content -LiteralPath $LogPath -Encoding UTF8
    } else {
        "rgptg config already present." | Add-Content -LiteralPath $LogPath -Encoding UTF8
    }

    $env:JAVA_HOME = $JdkHome
    $env:Path = "$JdkHome\bin;$env:Path"

    "Java version:" | Add-Content -LiteralPath $LogPath -Encoding UTF8
    & (Join-Path $JdkHome "bin\java.exe") -version 2>&1 | Add-Content -LiteralPath $LogPath -Encoding UTF8

    "Setting initial password..." | Add-Content -LiteralPath $LogPath -Encoding UTF8
    & (Join-Path $Neo4jHome "bin\neo4j-admin.bat") dbms set-initial-password $Password 2>&1 | Add-Content -LiteralPath $LogPath -Encoding UTF8

    "Starting Neo4j..." | Add-Content -LiteralPath $LogPath -Encoding UTF8
    & (Join-Path $Neo4jHome "bin\neo4j.bat") start 2>&1 | Add-Content -LiteralPath $LogPath -Encoding UTF8

    "Done." | Add-Content -LiteralPath $LogPath -Encoding UTF8
} catch {
    "ERROR: $($_.Exception.Message)" | Add-Content -LiteralPath $LogPath -Encoding UTF8
    throw
}
