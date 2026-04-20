with timeout of 7200 seconds
	try
		do shell script quoted form of "/opt/homebrew/bin/python3" & space & quoted form of "/Users/steve/Filter_Landscape_Photos/photos_landscape_last_scan.py"
	on error errMsg number errNum
		display dialog "啟動掃描控制器失敗：" & return & errMsg & " (" & errNum & ")" with title "Photos 增量扫描" buttons {"确定"}
	end try
end timeout
