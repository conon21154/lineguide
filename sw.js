// 서비스 워커 버전 (업데이트 시 변경)
const CACHE_NAME = 'circuit-search-v1.0.3';
const STATIC_CACHE_NAME = 'circuit-static-v1.0.3';
const DYNAMIC_CACHE_NAME = 'circuit-dynamic-v1.0.3';

// 캐시할 정적 파일들
const STATIC_FILES = [
  '/lineguide/',
  '/lineguide/index.html',
  '/lineguide/manifest.json',
  'https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js',
  '/lineguide/icon-192.png',
  '/lineguide/icon-512.png'
];

// 서비스 워커 설치
self.addEventListener('install', event => {
  console.log('서비스 워커 설치 중...');
  
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then(cache => {
        console.log('정적 파일 캐시 중...');
        return cache.addAll(STATIC_FILES);
      })
      .then(() => {
        console.log('서비스 워커 설치 완료');
        return self.skipWaiting(); // 즉시 활성화
      })
      .catch(error => {
        console.error('서비스 워커 설치 실패:', error);
      })
  );
});

// 서비스 워커 활성화
self.addEventListener('activate', event => {
  console.log('서비스 워커 활성화 중...');
  
  event.waitUntil(
    caches.keys()
      .then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => {
            // 이전 버전 캐시 삭제
            if (cacheName !== STATIC_CACHE_NAME && 
                cacheName !== DYNAMIC_CACHE_NAME && 
                cacheName.startsWith('circuit-')) {
              console.log('이전 캐시 삭제:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('서비스 워커 활성화 완료');
        return self.clients.claim(); // 모든 클라이언트 제어
      })
  );
});

// 네트워크 요청 가로채기 (캐시 우선 전략)
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);
  
  // HTML 파일은 네트워크 우선, 실패 시 캐시
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          // 성공적인 응답을 캐시에 저장
          const responseClone = response.clone();
          caches.open(DYNAMIC_CACHE_NAME)
            .then(cache => cache.put(request, responseClone));
          return response;
        })
        .catch(() => {
          // 네트워크 실패 시 캐시에서 가져오기
          return caches.match(request)
            .then(cachedResponse => {
              if (cachedResponse) {
                return cachedResponse;
              }
              // 캐시도 없으면 오프라인 페이지 또는 기본 페이지
              return caches.match('/');
            });
        })
    );
    return;
  }
  
  // 정적 리소스는 캐시 우선
  if (STATIC_FILES.includes(request.url) || 
      request.url.includes('cdnjs.cloudflare.com')) {
    event.respondWith(
      caches.match(request)
        .then(cachedResponse => {
          if (cachedResponse) {
            return cachedResponse;
          }
          
          // 캐시에 없으면 네트워크에서 가져와서 캐시
          return fetch(request)
            .then(response => {
              if (response.status === 200) {
                const responseClone = response.clone();
                caches.open(STATIC_CACHE_NAME)
                  .then(cache => cache.put(request, responseClone));
              }
              return response;
            });
        })
        .catch(() => {
          // 네트워크도 실패하면 기본 응답
          if (request.url.includes('.png') || request.url.includes('.jpg')) {
            // 이미지 요청 실패 시 기본 아이콘 반환
            return new Response('', { status: 404 });
          }
          return new Response('오프라인 상태입니다', { 
            status: 503,
            statusText: 'Service Unavailable'
          });
        })
    );
    return;
  }
  
  // 다른 요청들은 기본 네트워크 우선
  event.respondWith(
    fetch(request)
      .catch(() => {
        return caches.match(request);
      })
  );
});

// 백그라운드 동기화 (데이터 업데이트 알림)
self.addEventListener('sync', event => {
  console.log('백그라운드 동기화:', event.tag);
  
  if (event.tag === 'circuit-data-sync') {
    event.waitUntil(
      // 여기에 데이터 동기화 로직 구현
      syncCircuitData()
    );
  }
});

// 푸시 알림 수신
self.addEventListener('push', event => {
  console.log('푸시 알림 수신:', event);
  
  if (event.data) {
    const data = event.data.json();
    const options = {
      body: data.body || '새로운 회선 데이터가 업데이트되었습니다',
      icon: '/icon-192.png',
      badge: '/icon-72.png',
      tag: 'circuit-update',
      requireInteraction: true,
      actions: [
        {
          action: 'open',
          title: '앱 열기'
        },
        {
          action: 'close',
          title: '닫기'
        }
      ]
    };
    
    event.waitUntil(
      self.registration.showNotification(
        data.title || '회선선번장 업데이트',
        options
      )
    );
  }
});

// 알림 클릭 처리
self.addEventListener('notificationclick', event => {
  console.log('알림 클릭:', event);
  
  event.notification.close();
  
  if (event.action === 'open') {
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

// 데이터 동기화 함수
async function syncCircuitData() {
  try {
    console.log('회선 데이터 동기화 시작');
    
    // 여기에 서버에서 최신 데이터를 가져오는 로직 구현
    // 예: fetch('/api/circuits/latest')
    
    // 로컬 스토리지의 데이터와 비교하여 업데이트 필요 시 알림
    const clients = await self.clients.matchAll();
    clients.forEach(client => {
      client.postMessage({
        type: 'DATA_UPDATED',
        message: '새로운 회선 데이터가 있습니다'
      });
    });
    
    console.log('회선 데이터 동기화 완료');
  } catch (error) {
    console.error('데이터 동기화 실패:', error);
  }
}

// 캐시 크기 관리 (최대 50MB)
async function manageCacheSize(cacheName, maxSize = 50 * 1024 * 1024) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  
  let totalSize = 0;
  for (const key of keys) {
    const response = await cache.match(key);
    if (response) {
      const blob = await response.blob();
      totalSize += blob.size;
    }
  }
  
  // 크기 초과 시 오래된 캐시부터 삭제
  if (totalSize > maxSize) {
    const keysToDelete = keys.slice(0, Math.floor(keys.length / 2));
    await Promise.all(
      keysToDelete.map(key => cache.delete(key))
    );
    console.log(`캐시 정리 완료: ${keysToDelete.length}개 항목 삭제`);
  }
}

// 정기적인 캐시 정리 (1시간마다)
setInterval(() => {
  manageCacheSize(DYNAMIC_CACHE_NAME);
}, 60 * 60 * 1000);

console.log('서비스 워커 로드 완료');