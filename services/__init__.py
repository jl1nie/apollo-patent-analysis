"""APOLLO Private 用サービス層。

hosted モードでは import されても副作用ゼロ（各モジュール内で `apollo_config.IS_PRIVATE`
をチェックしてから動作する）。private モードでのみ実効的に動く。
"""
