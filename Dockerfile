# Используем легковесный официальный образ Python
FROM python:3.11-slim

# Устанавливаем tzdata для корректной работы часовых поясов (важно для pytz)
RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем временную зону Минск (Europe/Minsk)
ENV TZ=Europe/Minsk
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Рабочая директория
WORKDIR /app

# Копируем зависимости и код
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Запуск бота
CMD ["python", "main.py"]