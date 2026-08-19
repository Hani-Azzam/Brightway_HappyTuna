# How to run social network app (more info in social-network directory)
To use this project as a Docker container, first make sure you make and fill .env file (copy .env.example) then run these 2 commands inside social-network directory:
```
docker build -t social-network-app .    
docker run --env-file .env -p 3005:3000 -d social-network-app
```

You can check the Webapp at http://localhost:3005/app/
It comes preseeded with example data. If you want to reset it, you may run this command inside the container:
```
npx prisma migrate reset
```
