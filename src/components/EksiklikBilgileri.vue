<template>
  <div class="eksiklik-bilgileri">
    <!-- Devam Ediyor/Tamamlandı alanını kaldır -->
    <!-- <div class="durum-alani">
         <label>Durum:</label>
         <select v-model="durum">
           <option value="devam">Devam Ediyor</option>
           <option value="tamamlandi">Tamamlandı</option>
         </select>
         </div> -->
    <div class="cevaplandirma-tarihi">
      <label>Eksiklik Yazısı Cevaplandırma Tarihi:</label>
      <input 
        type="date" 
        v-model="cevaplandirmaTarihi"
        @change="tarihKaydet"
      >
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      cevaplandirmaTarihi: null
    }
  },
  methods: {
    tarihKaydet() {
      axios.post('/api/eksiklik/cevaplandirma-tarihi', {
        belgeId: this.belgeId,
        cevaplandirmaTarihi: this.cevaplandirmaTarihi
      })
      .then(response => {
        this.$notify({
          type: 'success',
          message: 'Cevaplandırma tarihi kaydedildi'
        });
      })
      .catch(error => {
        this.$notify({
          type: 'error',
          message: 'Tarih kaydedilirken bir hata oluştu'
        });
      });
    }
  }
}
</script>

<style scoped>
.cevaplandirma-tarihi {
  margin: 10px 0;
}

.cevaplandirma-tarihi label {
  display: block;
  margin-bottom: 5px;
}

.cevaplandirma-tarihi input {
  padding: 5px;
  border: 1px solid #ddd;
  border-radius: 4px;
}
</style> 