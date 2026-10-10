# ralph_loop.ps1 - Ralph Loop for CampusAI tasks
# Usage: .\ralph_loop.ps1
# Usage (dry run): .\ralph_loop.ps1 -DryRun
# Usage (custom agent): .\ralph_loop.ps1 -AgentCmd claude

param(
    [string]$PrdFile  = "PRD.md",
    [string]$AgentCmd = "claude",
    [int]$MaxIter     = 20,
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  RALPH LOOP - CampusAI Task Runner" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  PRD File : $PrdFile" -ForegroundColor Gray
Write-Host "  Agent    : $AgentCmd" -ForegroundColor Gray
Write-Host "  Max Iter : $MaxIter" -ForegroundColor Gray
if ($DryRun) { Write-Host "  MODE     : DRY RUN (agent not invoked)" -ForegroundColor Yellow }
Write-Host "=====================================================" -ForegroundColor Cyan

# Verify PRD exists
if (-not (Test-Path $PrdFile)) {
    Write-Host "ERROR: '$PrdFile' not found in: $(Get-Location)" -ForegroundColor Red
    Write-Host "Create PRD.md with tasks like:  - [ ] Task description" -ForegroundColor Yellow
    exit 1
}

for ($i = 1; $i -le $MaxIter; $i++) {
    Write-Host ""
    Write-Host "--- Iteration $i / $MaxIter ---" -ForegroundColor Cyan

    # Count unchecked tasks
    $remaining = Select-String -Path $PrdFile -Pattern "^- \[ \]" -ErrorAction SilentlyContinue
    
    if (-not $remaining -or $remaining.Count -eq 0) {
        Write-Host "All tasks complete!" -ForegroundColor Green
        break
    }

    Write-Host "Remaining tasks: $($remaining.Count)" -ForegroundColor Yellow
    $remaining | ForEach-Object { Write-Host "  $($_.Line.Trim())" -ForegroundColor Gray }

    # Get first unchecked task
    $nextTask = $remaining[0].Line.Trim() -replace "^- \[ \] ", ""
    Write-Host "Next task: $nextTask" -ForegroundColor White

    if ($DryRun) {
        Write-Host "[DRY RUN] Would invoke agent: $AgentCmd" -ForegroundColor Yellow
    } else {
        # Check if agent CLI is available
        $agentExists = Get-Command $AgentCmd -ErrorAction SilentlyContinue
        
        if ($agentExists) {
            Write-Host "Invoking $AgentCmd..." -ForegroundColor Cyan
            $prompt = "Read PRD.md. Implement this ONE task: $nextTask. Mark it done in PRD.md (- [ ] -> - [x]). Commit the changes. Then exit."
            
            if ($AgentCmd -eq "claude") {
                & claude --dangerously-skip-permissions --print $prompt
            } elseif ($AgentCmd -eq "aider") {
                & aider --message $prompt --yes
            } else {
                & $AgentCmd $prompt
            }
        } else {
            Write-Host ""
            Write-Host "Agent '$AgentCmd' not found. Running in MANUAL mode." -ForegroundColor Yellow
            Write-Host "---------- COPY THIS PROMPT INTO YOUR AI TOOL ----------" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Read PRD.md in the project directory." -ForegroundColor White
            Write-Host "Implement this ONE task: $nextTask" -ForegroundColor White
            Write-Host "Mark it done: change [ ] to [x] in PRD.md" -ForegroundColor White
            Write-Host "Commit: git add -A ; git commit -m 'ralph-loop: $nextTask'" -ForegroundColor White
            Write-Host ""
            Write-Host "---------------------------------------------------" -ForegroundColor Yellow
            Read-Host "Press ENTER when task is done in your AI tool"
        }
    }

    # Safety commit
    git add -A 2>$null
    $null = git diff --cached --quiet 2>$null
    if ($LASTEXITCODE -ne 0) {
        git commit -m "ralph-loop: safety commit iteration $i" 2>$null
        Write-Host "Safety commit made." -ForegroundColor Gray
    }

    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  RALPH LOOP FINISHED" -ForegroundColor Green

$done    = (Select-String -Path $PrdFile -Pattern "^- \[x\]" -ErrorAction SilentlyContinue).Count
$pending = (Select-String -Path $PrdFile -Pattern "^- \[ \]" -ErrorAction SilentlyContinue).Count

Write-Host "  Done    : $done tasks" -ForegroundColor Green
Write-Host "  Pending : $pending tasks" -ForegroundColor $(if ($pending -eq 0) { "Green" } else { "Yellow" })
Write-Host "=====================================================" -ForegroundColor Cyan
