<template>
  <div class="belge-listesi">
    <div v-for="belge in belgeler" :key="belge.id" class="belge-item">
      <span>{{ belge.ad }}</span>
      <!-- Silme butonu ekle -->
      <button @click="belgeSil(belge.id)" class="sil-btn">
        <i class="fas fa-trash"></i>
      </button>
    </div>
  </div>
</template>

<script>
export default {
  // ... mevcut kod ...
  methods: {
    belgeSil(belgeId) {
      // Silme işlemi için onay iste
      if (confirm('Bu belgeyi silmek istediğinizden emin misiniz?')) {
        // Belgeyi sil
        this.belgeler = this.belgeler.filter(belge => belge.id !== belgeId);
        // Backend'e silme isteği gönder
        this.belgeSilmeIstegiGonder(belgeId);
      }
    },
    
    belgeSilmeIstegiGonder(belgeId) {
      // API çağrısı
      axios.delete(`/api/belgeler/${belgeId}`)
        .then(response => {
          this.$notify({
            type: 'success',
            message: 'Belge başarıyla silindi'
          });
        })
        .catch(error => {
          this.$notify({
            type: 'error',
            message: 'Belge silinirken bir hata oluştu'
          });
        });
    }
  }
}
</script> 