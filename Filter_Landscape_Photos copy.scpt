-- 【全局防卡死超时设置】
with timeout of 3600 seconds
    
    tell application "Photos"
        -- ================= 配置区域 =================
        set sourceAlbumName to "𝕏"         -- 来源相册名
        set targetAlbumName to "橫向照片篩選" -- 目标相册名
        
        -- 【关键设置】你想扫描多少张？
        -- 模式 A (推荐): 写 5000 (只扫描最后 5000 张，速度快，适合增量)
        -- 模式 B (全量): 写 50000 (扫描所有 38307 张，第一次运行建议用这个，需几分钟)
        set scanLimit to 5000 
        
        -- 【技术参数】每次从硬盘读多少张？(保持 500 不要动，最稳)
        set readBatchSize to 500
        -- ===========================================
        
        -- 1. 准备目标相册
        if not (exists album named targetAlbumName) then
            make new album named targetAlbumName
        end if
        set targetAlbum to album targetAlbumName
        
        -- 2. 获取来源相册
        if not (exists album named sourceAlbumName) then
            display dialog "找不到普通相册: " & sourceAlbumName buttons {"确定"}
            return
        end if
        set currentAlbum to album sourceAlbumName
        
        -- 3. 计算扫描范围
        set totalCount to count of media items of currentAlbum
        display notification "相册总数: " & totalCount & " 张" with title "准备开始"
        
        if totalCount is 0 then return
        
        -- 计算起点：如果是全量模式，startIndex 就是 1
        set startIndex to totalCount - scanLimit + 1
        if startIndex < 1 then set startIndex to 1
        
        set processCount to 0
        set matchCount to 0
        set writeBuffer to {}
        
        -- =======================================
        -- 核心循环：切片读取 (从 startIndex 到 totalCount)
        -- =======================================
        repeat with i from startIndex to totalCount by readBatchSize
            
            -- 计算当前批次的结束点 (j)
            set j to i + readBatchSize - 1
            if j > totalCount then set j to totalCount
            
            try
                -- 【高速读取】一次读 500 张的引用 (Memory Safe)
                set currentBatch to media items i thru j of currentAlbum
                
                -- 内存筛选
                repeat with aPhoto in currentBatch
                    try
                        -- 只要是横图 (Width > Height)
                        if (width of aPhoto) > (height of aPhoto) then
                            copy aPhoto to end of writeBuffer
                            set matchCount to matchCount + 1
                        end if
                    end try
                end repeat
                
                -- 【写入磁盘】缓冲区有货就存
                if (count of writeBuffer) > 0 then
                    add writeBuffer to targetAlbum
                    set writeBuffer to {} -- 清空缓存
                end if
                
                -- 进度提示 (每处理 2000 张提示一次)
                set processCount to processCount + readBatchSize
                if (processCount mod 2000) < readBatchSize then
                    display notification "进度: " & j & " / " & totalCount & " (找到 " & matchCount & " 张)" with title "正在扫描..."
                end if
                
            on error
                -- 忽略读取错误的切片
            end try
            
        end repeat
        
        -- 写入剩余的
        if (count of writeBuffer) > 0 then
            add writeBuffer to targetAlbum
        end if
        
        beep 2
        display dialog "处理完成！" & return & "扫描范围：" & startIndex & " - " & totalCount & return & "共归档横图：" & matchCount & " 张" buttons {"确定"}
        
    end tell
    
end timeout