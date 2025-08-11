#!/bin/bash
# Ubuntu Database Setup Script for Han Dating Bot

echo "🚀 Setting up PostgreSQL and Redis on Ubuntu..."

# Update package list
echo "📋 Updating package list..."
sudo apt update

# Install PostgreSQL and Redis
echo "📦 Installing PostgreSQL and Redis..."
sudo apt install -y postgresql postgresql-contrib redis-server

# Install Python dependencies for database
echo "🐍 Installing Python database dependencies..."
pip install asyncpg psycopg2-binary redis aioredis

echo "✅ Installation complete!"
