with timeout of 7200 seconds
	tell application "Photos"
		-- ================= 配置 =================
		set sourceAlbumName to "𝕏"
		set targetAlbumName to "橫向照片篩選"
		set writeBatchSize to 20
		-- =======================================
		
		-- 1. 准备目标相册
		set targetAlbumList to every album whose name is targetAlbumName
		if targetAlbumList is {} then
			make new album named targetAlbumName
			set targetAlbumList to every album whose name is targetAlbumName
		end if
		set targetAlbum to item 1 of targetAlbumList
		
		-- 2. 读取上次扫描时间戳
		set baseDate to (current date)
		set year of baseDate to 1970
		set month of baseDate to January
		set day of baseDate to 1
		set time of baseDate to 0
		
		set lastCheckDate to baseDate
		try
			set savedEpoch to do shell script "cat ~/.photos_landscape_last_scan"
			set lastCheckDate to baseDate + (savedEpoch as integer)
		end try
		
		set currentRunDate to (current date)
		
		-- 3. 获取来源相册并计算总数
		set sourceAlbumsList to every album whose name is sourceAlbumName
		if sourceAlbumsList is {} then
			display dialog "找不到来源相册: " & sourceAlbumName buttons {"确定"}
			return
		end if
		
		set currentAlbum to item 1 of sourceAlbumsList
		set totalCount to count of media items of currentAlbum
		if totalCount is 0 then
			display notification "来源相册为空，无需扫描。" with title "无需更新"
			return
		end if
		
		set totalAdded to 0
		set bufferList to {}
		set processCount to 0
		
		display notification "总计 " & totalCount & " 张。启用 O(1) 单指针内存安全模式..." with title "开始扫描"
		
		-- 4. 倒序单指针遍历，避免构造大批量对象说明符
		repeat with i from totalCount to 1 by -1
			try
				set targetPhoto to media item i of currentAlbum
				
				if (date of targetPhoto) > lastCheckDate then
					if (width of targetPhoto) > (height of targetPhoto) then
						copy targetPhoto to end of bufferList
					end if
					
					set processCount to processCount + 1
				else
					exit repeat
				end if
				
				set targetPhoto to missing value
			on error
				-- 忽略单张坏图，继续扫描后续项目
			end try
			
			if (count of bufferList) is greater than or equal to writeBatchSize then
				try
					add bufferList to targetAlbum
					set totalAdded to totalAdded + (count of bufferList)
					set bufferList to {}
				end try
			end if
			
			if (processCount is not 0) and ((processCount mod 500) is 0) then
				display notification "已安全检查 " & processCount & " 张新照片..." with title "运行中"
			end if
		end repeat
		
		if (count of bufferList) > 0 then
			try
				add bufferList to targetAlbum
				set totalAdded to totalAdded + (count of bufferList)
				set bufferList to {}
			end try
		end if
		
		-- 5. 仅在成功跑完整个流程后更新时间戳
		set currentEpoch to currentRunDate - baseDate
		do shell script "echo " & currentEpoch & " > ~/.photos_landscape_last_scan"
		
		-- 6. 结果反馈
		beep
		if totalAdded > 0 then
			display dialog "增量整理完成！" & return & "共检查新照片：" & processCount & " 张" & return & "新增横图：" & totalAdded & " 张" buttons {"确定"}
		else
			display notification "本次检查了 " & processCount & " 张，没有发现新横图。" with title "无需更新"
		end if
	end tell
end timeout
