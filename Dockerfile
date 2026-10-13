FROM ubuntu:20.04

# منع النوافذ التفاعلية أثناء التثبيت
ENV DEBIAN_FRONTEND=noninteractive

# تثبيت الحزم المطلوبة (بما فيها OpenSSL 1.1 المتوافق)
RUN apt-get update && apt-get install -y \
    g++ build-essential libssl-dev zip unzip curl git \
    python3 python3-pip

# تجميع أداة zsign للتوقيع السريع (بدون -O3 لتجنب استهلاك الرام)
RUN git clone https://github.com/zhlynn/zsign.git /tmp/zsign && \
    cd /tmp/zsign && \
    g++ *.cpp common/*.cpp macho/*.cpp -o /usr/local/bin/zsign -lcrypto && \
    rm -rf /tmp/zsign

WORKDIR /app
COPY . /app

# تثبيت مكتبات البايثون
RUN pip3 install -no-cache-dir -r requirements.txt

# إنشاء المجلدات الضرورية لتجنب الأخطاء
RUN mkdir -p certs signed_ipas ipas images templates

# تشغيل البوت وواجهة الويب معاً
CMD ["python3", "main.py"]
