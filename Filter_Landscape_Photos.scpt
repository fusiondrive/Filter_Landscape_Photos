tell application "Photos"
    -- ================= 配置 =================
    set sourceAlbumName to "𝕏"
    set targetAlbumName to "橫向照片篩選"
    -- =======================================
    
    -- 1. 获取/创建目标相册
    if not (exists album named targetAlbumName) then
        make new album named targetAlbumName
    end if
    set targetAlbum to album targetAlbumName
    
    -- 2. 确定“时间锚点” (High Watermark)
    -- 【修复1：去本地化】使用对象属性构建日期，彻底解决 "1970年..." 报错
    set lastCheckDate to (current date)
    set year of lastCheckDate to 1970
    set month of lastCheckDate to January
    set day of lastCheckDate to 1
    set time of lastCheckDate to 0 -- 00:00:00
    
    -- 尝试读取目标相册最后一张照片的时间
    if (count of media items of targetAlbum) > 0 then
        try
            set lastPhoto to last media item of targetAlbum
            -- 这里的 date 是属性，通常不需要转义，但为了保险
            set lastCheckDate to date of lastPhoto
        on error
            -- 读取失败则维持 1970 默认值
        end try
    end if
    
    -- 3. 获取所有来源相册
    set sourceAlbumsList to every album whose name is sourceAlbumName
    
    set totalAdded to 0
    set batchSize to 100
    set landscapeList to {}
    
    repeat with currentAlbum in sourceAlbumsList
        -- 【修复2：关键字冲突】
        -- 使用 |date| (管道符) 包裹，强制指代“属性”，解决 -1700 错误
        -- 这里的逻辑是：从数据库只拉取比锚点时间更新的照片
        try
            set candidatePhotos to (every media item of currentAlbum whose |date| > lastCheckDate)
        on error
            -- 备用方案：如果 |date| 依然报错，尝试使用 explicit 引用
            set candidatePhotos to (every media item of currentAlbum whose date of it > lastCheckDate)
        end try
        
        repeat with aPhoto in candidatePhotos
            try
                -- 检查长宽比
                if (width of aPhoto) > (height of aPhoto) then
                    copy aPhoto to end of landscapeList
                end if
            end try
            
            -- 批处理写入
            if (count of landscapeList) is greater than or equal to batchSize then
                add landscapeList to targetAlbum
                set landscapeList to {}
                set totalAdded to totalAdded + batchSize
            end if
        end repeat
    end repeat
    
    -- 处理剩余队列
    if (count of landscapeList) > 0 then
        add landscapeList to targetAlbum
        set totalAdded to totalAdded + (count of landscapeList)
    end if
    
    -- 4. 结果反馈
    beep
    if totalAdded > 0 then
        display notification "增量更新完成，添加了 " & totalAdded & " 张照片" with title "照片整理"
    else
        display notification "没有发现晚于 " & (short date string of lastCheckDate) & " 的新照片" with title "无需更新"
    end if
    
end tell