# 批量处理脚本 - 自动断点续传
# 处理全部 465 个角色，每次 5 个，自动重试

$total = 465
$batchSize = 5
$processed = 0

Write-Host "=" * 60
Write-Host "开始批量处理 $total 个角色（每批 $batchSize 个）"
Write-Host "=" * 60

while ($processed -lt $total) {
    $remaining = $total - $processed
    $currentBatch = [Math]::Min($batchSize, $remaining)
    
    Write-Host "`n[批次 $($processed / $batchSize + 1)] 处理第 $($processed + 1) 到 $($processed + $currentBatch) 个角色..."
    
    try {
        Push-Location "d:\Workspace\ACG-Theogony"
        & "D:/Workspace/ACG-Theogony/.venv/Scripts/python.exe" -m backend.enrich_with_llm --limit $currentBatch --skip $processed --enrich-only
        Pop-Location
        
        $processed += $currentBatch
        Write-Host "[✓] 批次完成，已处理 $processed/$total 个"
        
        # 短暂休息
        Start-Sleep -Seconds 2
    }
    catch {
        Write-Host "[!] 批次出错: $_"
        Write-Host "[*] 等待 5 秒后重试..."
        Start-Sleep -Seconds 5
        # 不增加 $processed，重试相同批次
    }
}

Write-Host "`n" + "=" * 60
Write-Host "[✓] 全部完成！共处理 $total 个角色"
Write-Host "=" * 60
Write-Host "`n下一步: python -m backend.build_graph"
