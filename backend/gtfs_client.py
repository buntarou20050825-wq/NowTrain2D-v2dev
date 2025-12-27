"""
GTFS-RT（リアルタイム列車位置情報）を取得するクライアント
公共交通オープンデータセンター（ODPT）のAPIを使用
"""
import os
import logging
import requests
from google.transit import gtfs_realtime_pb2

logger = logging.getLogger(__name__)

# ODPTのGTFS-RTエンドポイント
ODPT_VEHICLE_POSITION_URL = "https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_trip_update"
ODPT_TRIP_UPDATE_URL = "https://api-challenge.odpt.org/api/v4/gtfs/realtime/jreast_odpt_train_trip_update"


class GtfsClient:
    """GTFS-RTデータを取得するクライアント"""
    
    def __init__(self):
        """環境変数からAPIキーを読み込む"""
        self.api_key = os.getenv("ODPT_API_KEY", "").strip()
        if not self.api_key:
            logger.warning("ODPT_API_KEY is not set in environment variables.")
    
    def fetch_vehicle_positions(self):
        """
        列車位置情報（VehiclePosition）を取得
        
        Returns:
            list: GTFS-RTのentityリスト。エラー時は空リスト。
        """
        return self._fetch_feed(ODPT_VEHICLE_POSITION_URL)
    
    def fetch_trip_updates(self):
        """
        遅延情報（TripUpdate）を取得
        ※ MS4-2以降で使用
        
        Returns:
            list: GTFS-RTのentityリスト。エラー時は空リスト。
        """
        return self._fetch_feed(ODPT_TRIP_UPDATE_URL)
    
    def _fetch_feed(self, url):
        """
        GTFS-RTフィードを取得してパースする共通処理
        
        Args:
            url (str): GTFS-RTエンドポイントURL
            
        Returns:
            list: FeedMessageのentityリスト
        """
        if not self.api_key:
            logger.warning("ODPT_API_KEY not set, returning empty list")
            return []
        
        
        try:
            # APIキーはクエリパラメータで送る
            params = {"acl:consumerKey": self.api_key}
            
            logger.info(f"Fetching GTFS-RT from {url}")
            logger.info(f"Params: {params}")
            # 接続タイムアウトと読み取りタイムアウトを分離
            resp = requests.get(url, params=params, timeout=(5, 10))
            logger.info(f"Status: {resp.status_code}")
            if resp.status_code != 200:
                logger.error(f"Response text: {resp.text}")
            resp.raise_for_status()
            
            logger.info(f"Received {len(resp.content)} bytes")
            
            # Protocol Buffersをパース
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(resp.content)
            
            # ヘッダー情報をログ出力
            if feed.HasField('header'):
                logger.info(f"Feed timestamp: {feed.header.timestamp}")
                logger.info(f"GTFS version: {feed.header.gtfs_realtime_version}")
            
            logger.info(f"Parsed {len(feed.entity)} entities")
            return feed.entity
            
        except requests.exceptions.Timeout:
            logger.error("GTFS-RT request timed out")
            return []
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error: {e.response.status_code}")
            if e.response.status_code == 401:
                logger.error("Authentication failed. Check ODPT_API_KEY.")
            elif e.response.status_code == 404:
                logger.error("Endpoint not found. Check URL.")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to parse GTFS-RT: {e}")
            return []
