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
	
	-- 2. 确定“时间锚点” (独立文件记录方案)
	-- 构建绝对安全的 1970 年基准时间 (Locale-safe)
	set baseDate to (current date)
	set year of baseDate to 1970
	set month of baseDate to January
	set day of baseDate to 1
	set time of baseDate to 0
	
	-- 尝试从隐藏文件中读取上次扫描的 Unix 时间戳 (纯秒数)
	set lastCheckDate to baseDate
	try
		-- 通过 shell 读取文件内容
		set savedEpoch to do shell script "cat ~/.photos_landscape_last_scan"
		-- 将秒数加回基准时间，还原为 AppleScript 的 Date 对象
		set lastCheckDate to baseDate + (savedEpoch as integer)
	on error
		-- 如果文件不存在（通常是第一次运行），则维持 1970 年默认值，全量扫描
	end try
	
	-- 记录本次脚本启动的精确时间，用于任务结束后写入
	set currentRunDate to (current date)
	
	-- 3. 获取所有来源相册
	set sourceAlbumsList to every album whose name is sourceAlbumName
	
	set totalAdded to 0
	set batchSize to 100
	set landscapeList to {}
	
	repeat with currentAlbum in sourceAlbumsList
		-- 使用 |date| 拉取比上次运行时间更新的照片
		try
			set candidatePhotos to (every media item of currentAlbum whose |date| > lastCheckDate)
		on error
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
	
	-- 4. 【核心新增】任务完成后，更新时间戳
	-- 计算本次运行时间距离 1970 年的秒数
	set currentEpoch to currentRunDate - baseDate
	-- 写入系统用户目录下的隐藏文件
	do shell script "echo " & currentEpoch & " > ~/.photos_landscape_last_scan"
	
	-- 5. 结果反馈
	beep
	if totalAdded > 0 then
		display notification "增量更新完成，添加了 " & totalAdded & " 张照片" with title "照片整理"
	else
		-- 格式化输出上次扫描时间以便确认
		set dateString to (short date string of lastCheckDate) & " " & (time string of lastCheckDate)
		display notification "没有发现晚于 " & dateString & " 的新照片" with title "无需更新"
	end if
	
end tell