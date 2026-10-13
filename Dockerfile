FROM ubuntu:22.04

# منع النوافذ التفاعلية أثناء التثبيت
ENV DEBIAN_FRONTEND=noninteractive

# تثبيت الحزم المطلوبة (تمت إضافة pkg-config المطلوبة للإصدار الجديد)
RUN apt-get update && apt-get install -y \
    g++ build-essential libssl-dev zip unzip curl git pkg-config \
    python3 python3-pip

# بناء أداة zsign بالطريقة الرسمية المحدثة باستخدام make
RUN git clone https://github.com/zhlynn/zsign.git /tmp/zsign && \
    cd /tmp/zsign/build/linux && \
    make && \
    cp zsign /usr/local/bin/zsign && \
    rm -rf /tmp/zsign

WORKDIR /app
COPY . /app

# تثبيت مكتبات البايثون
RUN pip3 install -no-cache-dir -r requirements.txt

# إنشاء المجلدات الضرورية لتجنب الأخطاء
RUN mkdir -p certs signed_ipas ipas images templates

# تشغيل السيرفر والبوت
CMD ["python3", "main.py"]
