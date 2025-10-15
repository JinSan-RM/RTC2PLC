import threading
import time

class SkipOnTimeoutMatcher:
    def __init__(self, expected_delay=0.5, tolerance=0.2, timeout=2.0):
        self.expected_delay = expected_delay
        self.tolerance = tolerance
        self.timeout = timeout
        
        self.vision_queue = []
        self.lock = threading.Lock()
        
        # 통계
        self.stats = {
            'matched': 0,
            'skipped': 0,
            'total_vision': 0,
            'total_breeze': 0
        }
    
    def on_vision_event(self, event_id, x_position=0):
        """Vision에서 물체 감지"""
        with self.lock:
            self.stats['total_vision'] += 1
            
            self.vision_queue.append({
                'id': event_id,
                'vision_time': time.time(),
                'expected_breeze_time': time.time() + self.expected_delay,
                'x_position': x_position,
                'status': 'pending'  # pending, matched, skipped
            })
            
            print(f"[Vision] 물체#{event_id} 감지 (큐 크기: {len(self.vision_queue)})")
    
    def on_breeze_event(self, classification):
        """Breeze에서 분류 결과 수신"""
        now = time.time()
        
        with self.lock:
            self.stats['total_breeze'] += 1
            
            if not self.vision_queue:
                print(f"[경고] Breeze 결과({classification}) 왔지만 대기 중인 Vision 없음")
                return None
            
            # 가장 오래된 pending 항목 찾기
            target_item = None
            for item in self.vision_queue:
                if item['status'] == 'pending':
                    target_item = item
                    break
            
            if not target_item:
                print(f"[경고] 모든 Vision 이벤트가 처리됨")
                return None
            
            # 타임스탬프 검증
            time_diff = now - target_item['expected_breeze_time']
            
            if abs(time_diff) < self.tolerance:
                # 정상 매칭
                target_item['status'] = 'matched'
                target_item['actual_time'] = now
                target_item['classification'] = classification
                self.stats['matched'] += 1
                
                delay = now - target_item['vision_time']
                print(f"[매칭] Vision#{target_item['id']} → {classification} "
                      f"(지연 {delay:.3f}s, 오차 {time_diff:.3f}s)")
                
                return {
                    'event_id': target_item['id'],
                    'classification': classification,
                    'matched': True
                }
            
            elif time_diff > self.tolerance:
                # 너무 늦음 - 이전 물체 누락
                print(f"[건너뛰기] Vision#{target_item['id']} 타임아웃")
                print(f"  예상 시간: {target_item['expected_breeze_time']:.3f}")
                print(f"  현재 시간: {now:.3f} (차이 {time_diff:.3f}s)")
                
                target_item['status'] = 'skipped'
                self.stats['skipped'] += 1
                
                # 다음 pending 항목 찾아서 재시도
                next_item = None
                for item in self.vision_queue:
                    if item['status'] == 'pending':
                        next_item = item
                        break
                
                if next_item:
                    next_time_diff = now - next_item['expected_breeze_time']
                    if abs(next_time_diff) < self.tolerance:
                        # 다음 항목과 매칭
                        next_item['status'] = 'matched'
                        next_item['classification'] = classification
                        self.stats['matched'] += 1
                        
                        print(f"[매칭] 다음 항목 Vision#{next_item['id']} → {classification}")
                        
                        return {
                            'event_id': next_item['id'],
                            'classification': classification,
                            'matched': True
                        }
                
                print(f"  → 분류 포기, 다음 Breeze 결과 대기")
                return None
            
            else:
                # 너무 빠름 - Breeze가 예상보다 빨리 도착
                print(f"[경고] 예상보다 빠른 Breeze 결과 ({-time_diff:.3f}s 빠름)")
                print(f"  → 대기 후 재확인")
                return None
    
    def cleanup_old_events(self):
        """오래된 이벤트 정리"""
        now = time.time()
        
        with self.lock:
            # 타임아웃 처리
            for item in self.vision_queue:
                if item['status'] == 'pending':
                    age = now - item['vision_time']
                    if age > self.timeout:
                        item['status'] = 'skipped'
                        self.stats['skipped'] += 1
                        print(f"[타임아웃] Vision#{item['id']} 제거 (경과 {age:.1f}s)")
            
            # 처리된 항목 제거 (최근 10개만 보관)
            processed = [item for item in self.vision_queue if item['status'] != 'pending']
            pending = [item for item in self.vision_queue if item['status'] == 'pending']
            
            self.vision_queue = pending + processed[-10:]
    
    def get_stats_report(self):
        """통계 리포트"""
        with self.lock:
            if self.stats['total_vision'] == 0:
                return "통계 없음"
            
            match_rate = (self.stats['matched'] / self.stats['total_vision']) * 100
            skip_rate = (self.stats['skipped'] / self.stats['total_vision']) * 100
            
            # Vision과 Breeze 개수 차이
            vision_breeze_diff = self.stats['total_vision'] - self.stats['total_breeze']
            
            return f"""
==================== 매칭 통계 ====================
Vision 감지:    {self.stats['total_vision']:4d}개
Breeze 분류:    {self.stats['total_breeze']:4d}개
차이:           {vision_breeze_diff:4d}개

성공 매칭:      {self.stats['matched']:4d}개 ({match_rate:5.1f}%)
건너뛰기:       {self.stats['skipped']:4d}개 ({skip_rate:5.1f}%)

현재 대기 큐:   {len([i for i in self.vision_queue if i['status']=='pending']):4d}개
==================================================
"""