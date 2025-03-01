# middleware.py
import requests
import datetime
import socket
import logging
import ntplib
import time
from typing import Tuple, Dict, Any, Optional
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from loguru import logger


class ConnectionTimeMiddleware:
    """
    Django middleware to verify internet connectivity and system time accuracy.
    """
    
    def __init__(self, get_response):
        """
        Initialize the middleware with Django's get_response.
        """
        self.get_response = get_response
        
        self.time_threshold_seconds = getattr(settings, 'TIME_THRESHOLD_SECONDS', 60)
        self.connectivity_timeout = getattr(settings, 'CONNECTIVITY_TIMEOUT', 5)
        self.ntp_servers = getattr(settings, 'NTP_SERVERS', [
            'pool.ntp.org',
            'time.google.com',
            'time.windows.com',
            'time.apple.com'
        ])
        self.connectivity_check_urls = getattr(settings, 'CONNECTIVITY_CHECK_URLS', [
            'https://www.google.com',
            'https://www.cloudflare.com',
            'https://www.amazon.com'
        ])
        
        self.last_check_time = 0
        self.check_interval = getattr(settings, 'CONNECTION_TIME_CHECK_INTERVAL', 60) 
        self.last_status = None
        
        self.redirect_on_failure = getattr(settings, 'REDIRECT_ON_FAILURE', True)
        self.failure_url = getattr(settings, 'CONNECTION_FAILURE_URL', '/connection-error/')
        self.exempt_urls = getattr(settings, 'CONNECTION_TIME_EXEMPT_URLS', [
            '/admin/', 
            '/static/', 
            '/media/',
            '/connection-error/'
        ])
        
        logger.info("ConnectionTimeMiddleware initialized")
    
    def check_internet_connection(self) -> Tuple[bool, str]:
        """
        Check if the system has internet connectivity.
        
        Returns:
            Tuple containing (is_connected, status_message)
        """
        # First check using socket connection to DNS
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=self.connectivity_timeout)
            logger.debug("Internet connection verified via DNS")
            return True, "Internet connection is available"
        except (socket.timeout, socket.error):
            logger.debug("DNS connection check failed, trying HTTP requests")
            pass
        
        # If DNS check fails, try HTTP requests
        for url in self.connectivity_check_urls:
            try:
                response = requests.get(url, timeout=self.connectivity_timeout)
                if response.status_code == 200:
                    logger.debug(f"Internet connection verified via HTTP to {url}")
                    return True, "Internet connection is available"
            except requests.RequestException:
                continue
        
        return False, "No internet connection available"
    
    def check_system_time(self) -> Tuple[bool, str, Optional[float]]:
        """
        Check if the system time is accurate compared to NTP servers.
        """
        if not self.check_internet_connection()[0]:
            return False, "Cannot verify time - no internet connection", None
        
        ntp_client = ntplib.NTPClient()
        
        for server in self.ntp_servers:
            try:
                response = ntp_client.request(server, timeout=self.connectivity_timeout)
                ntp_time = datetime.datetime.fromtimestamp(response.tx_time)
                local_time = datetime.datetime.now()
                
                time_difference = abs((ntp_time - local_time).total_seconds())
                
                if time_difference <= self.time_threshold_seconds:
                    return True, f"System time is accurate (within {time_difference:.2f} seconds)", time_difference
                else:
                    return False, f"System time is inaccurate (off by {time_difference:.2f} seconds)", time_difference
                
            except (ntplib.NTPException, socket.timeout, socket.error) as e:
                logger.debug(f"NTP check failed for {server}: {str(e)}")
                continue
        
        return False, "Failed to verify time accuracy - could not reach any NTP servers", None
    
    def verify(self) -> Dict[str, Any]:
        """
        Run all verifications and return a comprehensive status report.
        """
        current_time = time.time()
        
        # Return cached result if it's recent enough
        if current_time - self.last_check_time < self.check_interval and self.last_status:
            return self.last_status
        
        internet_status = self.check_internet_connection()
        time_status = self.check_system_time()
        
        status = {
            "timestamp": datetime.datetime.now().isoformat(),
            "internet": {
                "connected": internet_status[0],
                "message": internet_status[1]
            },
            "time": {
                "accurate": time_status[0],
                "message": time_status[1],
                "difference_seconds": time_status[2]
            },
            "all_checks_passed": internet_status[0] and time_status[0]
        }
        
        # Update cache
        self.last_check_time = current_time
        self.last_status = status
        
        return status
    
    def is_path_exempt(self, path: str) -> bool:
        """Check if the current path should be exempt from checks"""
        return any(path.startswith(exempt) for exempt in self.exempt_urls)
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        """
        Process the request and apply the middleware logic.
        """
        if self.is_path_exempt(request.path):
            return self.get_response(request)
        
        if request.path == '/api/connection-status/':
            return JsonResponse(self.verify())
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return self.get_response(request)
        
        status = self.verify()
        
        request.connection_time_status = status
        
        if not status["all_checks_passed"] and self.redirect_on_failure and not request.path == self.failure_url:
            from django.shortcuts import redirect
            return redirect(self.failure_url)
       
        return self.get_response(request)
