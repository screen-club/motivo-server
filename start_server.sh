echo "Starting server ..."
docker compose -f prod.docker-compose.yaml down
docker compose -f prod.docker-compose.yaml pull
docker compose -f prod.docker-compose.yaml up  -d 
echo "Server started"

