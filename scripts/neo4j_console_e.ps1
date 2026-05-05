$ErrorActionPreference = "Continue"

$Neo4jHome = "E:\neo4j-codex\neo4j-5.26.25"
$JdkHome = "E:\neo4j-codex\jdk-21"
$LogPath = "E:\neo4j-codex\console-rgptg.log"

$env:JAVA_HOME = $JdkHome
$env:Path = "$JdkHome\bin;$env:Path"

"==== rgptg neo4j console $(Get-Date -Format o) ====" | Set-Content -LiteralPath $LogPath -Encoding UTF8
"Neo4jHome=$Neo4jHome" | Add-Content -LiteralPath $LogPath -Encoding UTF8
"JdkHome=$JdkHome" | Add-Content -LiteralPath $LogPath -Encoding UTF8

& (Join-Path $Neo4jHome "bin\neo4j.bat") console 2>&1 | Add-Content -LiteralPath $LogPath -Encoding UTF8
