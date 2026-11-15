@echo off
rem Self-elevating launcher for setup-firewall.ps1
powershell -NoProfile -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','\"%~dp0setup-firewall.ps1\"'"
