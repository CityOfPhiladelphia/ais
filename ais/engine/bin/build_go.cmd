mkdir ..\log
CALL build_engine > ../log/build_log_%date:~-4,4%%date:~-10,2%%date:~-7,2%.txt 2> ../log/build_errors_%date:~-4,4%%date:~-10,2%%date:~-7,2%.txt
